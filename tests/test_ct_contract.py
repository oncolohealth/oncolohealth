"""Synthetic box/worker fixtures; actual CT model runs are reported separately."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cancer_workbench.research import ct,runtime as rt

@unittest.skipUnless(importlib.util.find_spec('numpy') is not None,'optional NumPy not installed')
class CTBoxTests(unittest.TestCase):
    def test_reference_comparison_uses_lps_centre_size_and_discloses_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'key.json';p.write_text(json.dumps({'coordinate_system':'LPS','box_format':'cccwhd','input_sha256':'a'*64,'boxes_mm':[[0,0,0,4,4,4]]}),encoding='utf-8')
            result=ct.compare_reference({'boxes_world_LPS_cccwhd':[[0,0,0,4,4,4],[30,0,0,4,4,4]],'scores':[.9,.1]},p,'a'*64)
            self.assertEqual(result['agreement'][0]['matched'],1)
            self.assertEqual(result['agreement'][0]['unmatched_detections'],1)
            self.assertEqual(result['agreement'][1]['detections'],1)
            self.assertEqual(result['agreement'][1]['matches'][0]['IoU'],1.)
            self.assertIn('not independent',result['meaning'])

    def test_wrong_input_or_negative_reference_extents_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'key.json'
            p.write_text(json.dumps({'coordinate_system':'LPS','box_format':'cccwhd','input_sha256':'a'*64,'boxes_mm':[[0,0,0,-1,2,3]]}),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'positive'):
                ct.compare_reference({'boxes_world_LPS_cccwhd':[],'scores':[]},p,'a'*64)
            with self.assertRaisesRegex(ValueError,'matching input'):
                ct.compare_reference({'boxes_world_LPS_cccwhd':[],'scores':[]},p,'b'*64)

    def test_no_detections_still_produces_an_observed_empty_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'key.json';p.write_text(json.dumps({'coordinate_system':'LPS','box_format':'cccwhd','input_sha256':'a'*64,'boxes_mm':[]}),encoding='utf-8')
            result=ct.compare_reference({'boxes_world_LPS_cccwhd':[],'scores':[]},p,'a'*64)
            self.assertEqual(result['agreement'][0]['detections'],0)
            self.assertEqual(result['agreement'][0]['reference_boxes'],0)


class CTWorkerContractTests(unittest.TestCase):
    def test_reference_is_not_worker_input_and_detection_is_not_a_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            patches=[]
            for name,value in {'INPUTS':root/'inputs','REFERENCES':root/'keys','RESULTS':root/'observations'}.items():
                p=mock.patch.object(rt,name,value);p.start();patches.append(p)
            try:
                rt.INPUTS.mkdir();raw=b'synthetic structural volume fixture';sha=hashlib.sha256(raw).hexdigest()
                path=rt.INPUTS/(sha+'.nii.gz');path.write_bytes(raw)
                rt._save(rt.INPUTS/(sha+'.json'),{'id':sha,'file':path.name,'sha256':sha,'bytes':len(raw),'format':'nifti'})
                reference=rt.INPUTS/'separate.json';reference.write_text('{}',encoding='utf-8')
                reference_sha=rt.sha_file(reference)
                rt._save(rt.REFERENCES/sha/'fixture-ct.json',{'model_id':'fixture-ct','input_sha256':sha,'reference_input_id':'b'*64,
                     'reference_sha256':reference_sha,'reference_convention':'LPS_cccwhd'})
                model={'id':'fixture-ct','state':'verified','classes':['pulmonary_nodule'],'backend':'ct','formats':['nifti'],'training':{},'preprocessing':{},'implementation_sha256':'fixture','limitations':['synthetic fixture']}
                rt._save(root/'manifest.json',model)
                events=[];original_resolve=rt.resolve_input
                def resolve(input_id):
                    if input_id=='b'*64:
                        events.append('reference read');return reference,{'sha256':reference_sha,'format':'structured'}
                    return original_resolve(input_id)
                class Worker:
                    returncode=0
                    def __init__(self,argv,**kwargs):
                        self.argv=argv;events.append('worker')
                        assert 'b'*64 not in argv and str(reference) not in argv
                        out=Path(argv[argv.index('--out')+1]);png=out/'overlay.png';png.write_bytes(b'synthetic overlay')
                        rt._save(out/'detector-result.json',{'detection':{'count':0,'scores':[],'boxes_voxel_xyzxyz':[],
                            'boxes_world_LPS_cccwhd':[],'overlay_path':str(png),'overlay_sha256':rt.sha_file(png)},
                            'weights_sha256':'fixture','model_revision':'fixture'})
                    def wait(self,timeout):return 0
                with mock.patch.object(rt,'profile',return_value=(root,model)),mock.patch.object(rt,'resolve_input',side_effect=resolve), \
                     mock.patch.object(ct,'validate'),mock.patch('subprocess.Popen',Worker), \
                     mock.patch.object(ct,'compare_reference',return_value={'agreement':[],'meaning':'fixture only'}):
                    result=rt.predict('fixture-ct',sha)
                self.assertEqual(result['status'],'ok',result.get('error'));self.assertEqual(result['kind'],'detection')
                self.assertNotIn('prediction',result);self.assertNotIn('segmentation',result)
                self.assertEqual(events,['worker','reference read'])
                self.assertTrue(result['detection']['overlay_media'].startswith('research-output/'))
            finally:
                for patch in reversed(patches):patch.stop()

if __name__=='__main__':unittest.main()
