"""Pinned MONAI nodule detector on a real local CT series; no reference boxes enter inference.

CPU demonstration uses a 192x192x80 sliding ROI (publisher training patch size)
instead of the larger published inference ROI. It is a separately recorded
memory-bounded serving configuration, not a reproduced publisher benchmark.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import time,threading,uuid

from ..common.paths import MODELS_DIR
BUNDLE=MODELS_DIR/'monai-lung-nodule-ct-detection'
WEIGHT_SHA256='b5e79231466adae93a6fe8e8594029e9add142914e223b879aa0343bb2402d01'
REVISION='9d6622fda0e52be0a4155fed2e0afb9c17bcd80b'
LOCK=threading.Lock()
_DETECTOR=None
MARKER=b'ONCO:CT_HU;LIDC-DICOM-geometry'

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as stream:
  for b in iter(lambda:stream.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def prepare_dicom_series(directory: Path,destination: Path,provenance: Path) -> dict:
 """Decode one geometric CT series to HU; never inspect a reference label/box."""
 import numpy as np
 import nibabel as nib
 import pydicom
 paths=sorted(Path(directory).rglob('*.dcm'))
 if not 16<=len(paths)<=1024:raise ValueError('Requires one CT series with16–1024 slices.')
 slices=[pydicom.dcmread(p) for p in paths]
 first=slices[0]
 if len({str(s.SeriesInstanceUID) for s in slices})!=1 or any(str(s.Modality)!='CT' for s in slices):
  raise ValueError('Use exactly one CT series, not a mixed study or a different modality.')
 if any(int(s.Rows)!=int(first.Rows) or int(s.Columns)!=int(first.Columns) for s in slices):raise ValueError('CT slice dimensions differ.')
 orient=np.asarray(first.ImageOrientationPatient,dtype=float)
 spacing=np.asarray(first.PixelSpacing,dtype=float)
 if orient.shape!=(6,) or not np.isfinite(orient).all() or spacing.shape!=(2,) or not np.isfinite(spacing).all() or (spacing<=0).any():
  raise ValueError('CT orientation and pixel spacing must be finite with strictly positive spacing.')
 for s in slices:
  if any(name not in s for name in ['RescaleSlope','RescaleIntercept','RescaleType','SliceThickness']):
   raise ValueError('CT requires explicit HU calibration and slice thickness; missing values are not assumed.')
  calibration=np.asarray([float(s.RescaleSlope),float(s.RescaleIntercept),float(s.SliceThickness)])
  if not np.isfinite(calibration).all() or calibration[0]==0 or calibration[2]<=0:
   raise ValueError('CT calibration must be finite with nonzero slope and positive thickness.')
 if not np.allclose(np.linalg.norm(orient[:3]),1,atol=1e-4) or not np.allclose(np.linalg.norm(orient[3:]),1,atol=1e-4) or abs(np.dot(orient[:3],orient[3:]))>1e-4:
  raise ValueError('DICOM orientation vectors must be orthonormal.')
 if any(not np.allclose(np.asarray(s.ImageOrientationPatient,dtype=float),orient,atol=1e-4) or not np.allclose(np.asarray(s.PixelSpacing,dtype=float),spacing,atol=1e-4) for s in slices):
  raise ValueError('Changing orientation or pixel spacing within one series is unsupported.')
 normal=np.cross(orient[:3],orient[3:])
 ordered=sorted(zip(paths,slices),key=lambda ps:float(np.dot(np.asarray(ps[1].ImagePositionPatient,dtype=float),normal)))
 positions=np.asarray([np.asarray(s.ImagePositionPatient,dtype=float) for _,s in ordered])
 if not np.isfinite(positions).all():raise ValueError('CT slice positions must be finite.')
 distances=positions@normal;deltas=np.diff(distances);z_spacing=float(np.median(deltas))
 if z_spacing<=0 or not np.allclose(deltas,z_spacing,atol=.02,rtol=.01):raise ValueError('CT slices must be regularly spaced without duplicate positions or gaps.')
 if z_spacing>2.5 or max(float(s.SliceThickness) for _,s in ordered)>2.5:raise ValueError('This LUNA16-style path requires source slice thickness/spacing at most2.5mm; resampling a thicker scan does not restore missing information.')
 expected=positions[0]+np.arange(len(positions))[:,None]*normal*z_spacing
 if not np.allclose(positions,expected,atol=.05):raise ValueError('Gantry tilt or drifting slice origins need a separately validated geometry conversion.')
 values=[]
 for _,s in ordered:
  if str(s.RescaleType).upper() != 'HU':raise ValueError('Unrecognized CT rescale units.')
  values.append(s.pixel_array.astype(np.float32)*float(s.RescaleSlope)+float(s.RescaleIntercept))
 array=np.stack(values,axis=-1)
 if not np.isfinite(array).all():raise ValueError('CT calibrated voxels must be finite.')
 affine_lps=np.eye(4)
 affine_lps[:3,0]=orient[3:]*spacing[0]
 affine_lps[:3,1]=orient[:3]*spacing[1]
 affine_lps[:3,2]=normal*z_spacing
 affine_lps[:3,3]=positions[0]
 affine_ras=np.diag([-1.,-1.,1.,1.])@affine_lps
 image=nib.Nifti1Image(array,affine_ras);image.header['descrip']=MARKER;image.header.set_xyzt_units('mm')
 if Path(destination).exists():raise FileExistsError('Preserve existing prepared CT.')
 nib.save(image,destination)
 receipt={'created_utc':datetime.now(timezone.utc).isoformat(),'series_uid':str(first.SeriesInstanceUID),
  'source_files':[{'file':str(p.relative_to(directory)),'sha256':sha(p)} for p,_ in ordered],
  'prepared':str(destination),'prepared_sha256':sha(destination),'shape':list(array.shape),
  'source_spacing_mm':[float(spacing[0]),float(spacing[1]),z_spacing],'affine_RAS':affine_ras.tolist(),
  'intensity':'Per-slice stored values * RescaleSlope + RescaleIntercept, float32 HU',
  'units':'mm','reference_used':False,'medical_validation':False}
 Path(provenance).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
 return receipt

def validate(path: Path):
 import nibabel as nib
 import numpy as np
 image=nib.load(path)
 if len(image.shape)!=3 or not all(16<=d<=1024 for d in image.shape):raise ValueError('Requires one3D CT volume, not a28-voxel classification patch or MRI.')
 import math
 if math.prod(image.shape)>80_000_000:
  raise ValueError('This bounded CPU path supports at most80million source voxels.')
 spacing=list(map(float,image.header.get_zooms()[:3]))
 if not np.isfinite(spacing).all() or any(s<=0 for s in spacing) or not np.isfinite(image.affine).all() or abs(np.linalg.det(image.affine[:3,:3]))<1e-12:
  raise ValueError('CT requires finite physical geometry and positive voxel spacing.')
 if math.prod(max(1,round((n-1)*s/q)+1) for n,s,q in zip(image.shape,spacing,[.703125,.703125,1.25]))>100_000_000:
  raise ValueError('The resampled CT exceeds this PC CPU path limit of100million voxels.')
 if bytes(image.header['descrip']).rstrip(b'\0')!=MARKER or image.header.get_xyzt_units()[0]!='mm':
  raise ValueError('Use an explicitly prepared HU CT with verified DICOM geometry; units/orientation are never inferred from a filename.')
 if not np.isfinite(np.asanyarray(image.dataobj)).all():raise ValueError('CT calibrated voxels must be finite.')
 return {'shape':list(image.shape),'spacing_mm':list(map(float,image.header.get_zooms()[:3]))}

def detector():
 global _DETECTOR
 import torch
 from monai.networks.nets.resnet import resnet50
 from monai.apps.detection.networks.retinanet_network import RetinaNet,resnet_fpn_feature_extractor
 from monai.apps.detection.networks.retinanet_detector import RetinaNetDetector
 from monai.apps.detection.utils.anchor_utils import AnchorGeneratorWithAnchorShape
 provenance=json.loads((BUNDLE/'PROVENANCE.json').read_text(encoding='utf-8-sig'))
 expected=next(r['sha256'] for r in provenance['files'] if r['path']=='models/model.pt')
 if expected!=WEIGHT_SHA256 or provenance['source']['revision']!=REVISION or sha(BUNDLE/'models/model.pt')!=expected:raise ValueError('Pinned lung model byte identity changed.')
 if _DETECTOR is None:
  backbone=resnet50(spatial_dims=3,n_input_channels=1,conv1_t_stride=[2,2,1],conv1_t_size=[7,7,7])
  extractor=resnet_fpn_feature_extractor(backbone,3,False,[1,2],None)
  network=RetinaNet(spatial_dims=3,num_classes=1,num_anchors=3,feature_extractor=extractor,size_divisible=[16,16,8],use_list_output=False)
  network.load_state_dict(torch.load(BUNDLE/'models/model.pt',map_location='cpu',weights_only=True),strict=True)
  network.eval()
  anchors=AnchorGeneratorWithAnchorShape(feature_map_scales=[1,2,4],base_anchor_shapes=[[6,8,4],[8,6,5],[10,10,6]])
  _DETECTOR=RetinaNetDetector(network,anchors,spatial_dims=3,num_classes=1,size_divisible=[16,16,8])
  _DETECTOR.eval();_DETECTOR.set_target_keys(box_key='box',label_key='label')
  _DETECTOR.set_box_selector_parameters(score_thresh=.02,topk_candidates_per_level=1000,nms_thresh=.22,detections_per_img=300)
  _DETECTOR.set_sliding_window_inferer(roi_size=[192,192,80],overlap=.25,sw_batch_size=1,mode='constant',device='cpu')
 return _DETECTOR,expected

def run(path: Path,output_dir: Path,threads=6):
 import numpy as np
 import torch
 from PIL import Image,ImageDraw
 from monai.transforms import Compose,LoadImaged,EnsureChannelFirstd,Orientationd,Spacingd,ScaleIntensityRanged,EnsureTyped
 from monai.apps.detection.transforms.dictionary import ClipBoxToImaged,AffineBoxToWorldCoordinated,ConvertBoxModed
 started=time.monotonic();inspected=validate(path);input_hash=sha(path)
 torch.set_num_threads(max(1,min(int(threads),8)))
 pre=Compose([LoadImaged('image'),EnsureChannelFirstd('image'),Orientationd('image',axcodes='RAS'),
              Spacingd('image',pixdim=[.703125,.703125,1.25],mode='bilinear'),
              ScaleIntensityRanged('image',a_min=-1024.,a_max=300.,b_min=0.,b_max=1.,clip=True),EnsureTyped('image')])
 data=pre({'image':str(path)});image=data['image']
 print(json.dumps({'phase':'CT_preprocessed','shape':list(image.shape),'seconds':time.monotonic()-started}),flush=True)
 with LOCK:
  net,weight_sha=detector()
  with torch.inference_mode():
   prediction=net([image],use_inferer=True)[0]
 voxel_boxes=prediction['box'].detach().cpu().numpy();scores=prediction['label_scores'].detach().cpu().numpy()
 post=Compose([ClipBoxToImaged(box_keys='box',label_keys='label',box_ref_image_keys='image',remove_empty=True),
               AffineBoxToWorldCoordinated(box_keys='box',box_ref_image_keys='image',affine_lps_to_ras=True),
               ConvertBoxModed(box_keys='box',src_mode='xyzxyz',dst_mode='cccwhd')])
 world=post({'image':image,**prediction})['box'].detach().cpu().numpy()
 if sha(path)!=input_hash:raise ValueError('CT input changed during inference.')
 output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True);obs=uuid.uuid4().hex
 z=int(np.clip((voxel_boxes[0,2]+voxel_boxes[0,5])/2,0,image.shape[3]-1)) if len(voxel_boxes) else image.shape[3]//2
 plane=image[0,:,:,z].detach().cpu().numpy().T
 preview=Image.fromarray(np.uint8(np.clip(plane,0,1)*255)).convert('RGB');draw=ImageDraw.Draw(preview)
 for box,score in zip(voxel_boxes,scores):
  if box[2]<=z<=box[5] and score>=.5:
   draw.rectangle([float(box[0]),float(box[1]),float(box[3]),float(box[4])],outline='#fb7663',width=2)
 overlay=output_dir/('ct-'+obs+'-detections.png');preview.save(overlay)
 result={'id':obs,'status':'ok','kind':'detection','input_sha256':input_hash,'input':inspected,
  'model_id':'monai-lung-retinanet-local','weights_sha256':weight_sha,
  'model_revision':json.loads((BUNDLE/'PROVENANCE.json').read_text())['source']['revision'],
  'preprocessing':{'HU_window':[-1024,300],'scaled_to':[0,1],'orientation':'RAS','spacing_mm':[.703125,.703125,1.25],
                   'actual_tensor_shape':list(image.shape),'sliding_roi':[192,192,80],'overlap':.25,'CPU_float32':True,
                   'variant':'Memory-bounded publisher-training-size ROI; not the larger published inference configuration.'},
  'detection':{'count':len(scores),'class':'pulmonary_nodule','score_meaning':'Uncalibrated nodule detection scores, not malignancy/cancer probabilities.',
               'boxes_voxel_xyzxyz':voxel_boxes.tolist(),'boxes_world_LPS_cccwhd':world.tolist(),'scores':scores.tolist(),
               'overlay_path':str(overlay),'overlay_sha256':sha(overlay),'overlay_slice_index':z,'overlay_display_threshold':.5,
               'selector_threshold':.02,'nms_threshold':.22},
  'seconds':round(time.monotonic()-started,3),'device':'cpu','reference_used_for_inference':False,
  'limitations':['Publisher fold0 validation case; already used for model selection, not an independent test.',
                 'Different memory-bounded ROI from the published inference settings; no publisher benchmark reproduction.',
                 'Nodule detection is not a cancer diagnosis. No medical validation or established cancer-detection performance.']}
 (output_dir/('ct-'+obs+'-receipt.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 return result


def compare_reference(predicted: dict, reference_path: Path, input_sha256: str) -> dict:
 """Post-inference box agreement. Never called during detection/preprocessing."""
 import numpy as np
 reference=json.loads(Path(reference_path).read_text(encoding='utf-8-sig'))
 if reference.get('coordinate_system')!='LPS' or reference.get('box_format')!='cccwhd' or reference.get('input_sha256')!=input_sha256:
  raise ValueError('Reference must declare matching input SHA-256 and LPS centre/size box convention.')
 boxes=np.asarray(reference.get('boxes_mm'),dtype=np.float64)
 if boxes.size==0:boxes=np.empty((0,6))
 if boxes.ndim!=2 or boxes.shape[1]!=6 or not np.isfinite(boxes).all() or (boxes[:,3:]<=0).any():
  raise ValueError('Reference boxes must be finite N×6 centre xyz plus strictly positive width/height/depth in mm.')
 pred=np.asarray(predicted['boxes_world_LPS_cccwhd'],dtype=np.float64).reshape(-1,6)
 scores=np.asarray(predicted['scores'])
 low=np.maximum(pred[:,None,:3]-pred[:,None,3:]/2,boxes[None,:,:3]-boxes[None,:,3:]/2)
 high=np.minimum(pred[:,None,:3]+pred[:,None,3:]/2,boxes[None,:,:3]+boxes[None,:,3:]/2)
 intersection=np.maximum(high-low,0).prod(2)
 union=pred[:,3:].prod(1)[:,None]+boxes[:,3:].prod(1)[None,:]-intersection
 iou=np.divide(intersection,union,out=np.zeros_like(intersection),where=union>0)
 summaries=[]
 for threshold in [.02,.5]:
  indices=np.where(scores>=threshold)[0];used=set();matches=[]
  for i in sorted(indices,key=lambda j:-float(scores[j])):
   available=[j for j in range(len(boxes)) if j not in used]
   if not available:continue
   j=max(available,key=lambda k:float(iou[i,k]))
   if iou[i,j]>=.1:
    used.add(j);matches.append({'detection_index':int(i),'reference_index':int(j),'IoU':float(iou[i,j])})
  summaries.append({'score_threshold':threshold,'IoU_matching_threshold':.1,'detections':len(indices),'reference_boxes':len(boxes),
                   'matched':len(matches),'unmatched_detections':len(indices)-len(matches),'unmatched_references':len(boxes)-len(matches),'matches':matches})
 return {'coordinate_system':'LPS','box_format':'cccwhd','reference_sha256':sha(reference_path),
         'reference_boxes':len(boxes),'agreement':summaries,
         'meaning':'Single publisher-validation case, already used for model selection, and a different CPU ROI. Box overlap only; not independent accuracy, cancer probability or medical validation.'}
