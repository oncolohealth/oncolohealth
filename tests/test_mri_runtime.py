"""Synthetic structural fixtures only; real MRI execution is recorded separately."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    import nibabel as nib
    import numpy as np
except ImportError:
    nib = np = None

from cancer_workbench.research import runtime as rt, mri


@unittest.skipUnless(nib is not None and np is not None, "optional NumPy/NiBabel imaging runtime not installed")
class MRIRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name,path in {"INPUTS":self.root/"inputs","REFERENCES":self.root/"references",
                          "RESULTS":self.root/"observations","ARTIFACTS":self.root/"models",
                          "DATA_DIR":self.root/"data","MODELS_DIR":self.root/"weights"}.items():
            patch=mock.patch.object(rt,name,path);patch.start();self.addCleanup(patch.stop)

    def make_source(self):
        path=self.root/"source.nii.gz"
        a=np.stack([np.full((16,16,16),v,dtype=np.float32) for v in (10,20,30,40)],axis=-1)
        nib.save(nib.Nifti1Image(a,np.eye(4)),path)
        return path

    def prepare(self):
        src=self.make_source();dst=self.root/"prepared.nii.gz"
        mri.prepare_msd_input(src,dst,self.root/"provenance.json")
        return src,dst

    def upload(self,path):
        with mock.patch("cancer_workbench.acquisition.budget.check",return_value=(True,{})):
            return rt.upload({"name":path.name,"data":base64.b64encode(path.read_bytes()).decode()})

    def test_channel_order_is_explicit_and_reordering_preserves_geometry(self):
        source,prepared=self.prepare()
        with self.assertRaisesRegex(ValueError,"undeclared"):
            mri.validate(source)
        info=mri.validate(prepared)
        self.assertEqual(info["channel_order"],["T1ce","T1","T2","FLAIR"])
        self.assertEqual(np.asarray(nib.load(prepared).dataobj)[0,0,0].tolist(),[30,20,40,10])
        np.testing.assert_array_equal(nib.load(prepared).affine,nib.load(source).affine)

    def test_wrong_geometry_or_single_sequence_cannot_enter_inference(self):
        _,prepared=self.prepare();image=nib.load(prepared)
        wrong=self.root/"wrong.nii.gz";header=image.header.copy()
        nib.save(nib.Nifti1Image(np.zeros((16,16,16),dtype=np.uint8),np.eye(4),header),wrong)
        with self.assertRaisesRegex(ValueError,"four aligned"):
            mri.validate(wrong)
        affine=np.diag([2.,2.,2.,1.])
        nib.save(nib.Nifti1Image(np.asanyarray(image.dataobj),affine,image.header),wrong)
        with self.assertRaisesRegex(ValueError,"1 mm"):
            mri.validate(wrong)

    def test_reference_convention_maps_different_region_codes(self):
        predicted=np.zeros((2,2,2),dtype=np.uint8);truth=predicted.copy()
        predicted[0,0,0]=4;truth[0,0,0]=3
        predicted[0,0,1]=1;truth[0,0,1]=2
        predicted[0,1,0]=2;truth[0,1,0]=1
        p=self.root/"pred.nii.gz";r=self.root/"ref.nii.gz"
        nib.save(nib.Nifti1Image(predicted,np.eye(4)),p);nib.save(nib.Nifti1Image(truth,np.eye(4)),r)
        comparison=mri.compare_reference(p,r)
        self.assertTrue(all(v["dice_agreement"]==1. for v in comparison["regions"].values()))
        truth[1,1,1]=4;nib.save(nib.Nifti1Image(truth,np.eye(4)),r)
        with self.assertRaisesRegex(ValueError,"Mask labels"):
            mri.compare_reference(p,r)

    def test_external_artifact_paths_cannot_leave_models_root(self):
        folder=rt.ARTIFACTS/"fixture";folder.mkdir(parents=True)
        rt._save(folder/"manifest.json",{"id":"fixture","state":"verified","files":{},
                 "external_files":{"../outside":"0"*64}})
        with self.assertRaisesRegex(ValueError,"external specialist"):
            rt.profile("fixture")

    def test_runtime_keeps_segmentation_and_comparison_out_of_classifier_fields(self):
        _,prepared=self.prepare();meta=self.upload(prepared)
        ref=self.root/"ref.nii.gz";nib.save(nib.Nifti1Image(np.zeros((16,16,16),dtype=np.uint8),np.eye(4)),ref)
        ref_meta=self.upload(ref)
        model={"id":"fixture-mri","backend":"mri","formats":["nifti"],"classes":["whole_tumor"],
               "training":{"synthetic_test_fixture":True},"preprocessing":{"synthetic":True},"limitations":["fixture only"]}
        folder=self.root/"fixture-mri";folder.mkdir();rt._save(folder/"manifest.json",model)
        events=[]
        def infer(path,out):
            events.append("inference");self.assertEqual(path.name,meta["file"])
            out.mkdir(parents=True)
            mask=out/"mask.nii.gz";nib.save(nib.Nifti1Image(np.zeros((16,16,16),dtype=np.uint8),np.eye(4)),mask)
            overlay=out/"overlay.png";overlay.write_bytes(b"synthetic fixture")
            return {"segmentation":{"mask_path":str(mask),"mask_sha256":rt.sha_file(mask),
                    "overlay_path":str(overlay),"overlay_sha256":rt.sha_file(overlay),"region_voxels":{"whole_tumor":0}},
                    "weights_sha256":"fixture","model_revision":"fixture","implementation_sha256":"fixture"}
        def compare(*args):
            events.append("comparison");return {"regions":{},"limitation":"synthetic fixture only"}
        with mock.patch.object(rt,"profile",return_value=(folder,model)):
            with self.assertRaisesRegex(ValueError,"reference_convention"):
                rt.set_reference({"input_id":meta["id"],"model_id":model["id"],"reference_input_id":ref_meta["id"]})
            rt.set_reference({"input_id":meta["id"],"model_id":model["id"],"reference_input_id":ref_meta["id"],"reference_convention":"MSD_Task01"})
            with mock.patch.object(mri,"run",side_effect=infer),mock.patch.object(mri,"compare_reference",side_effect=compare):
                result=rt.predict(model["id"],meta["id"])
        self.assertEqual(result["status"],"ok");self.assertEqual(result["kind"],"segmentation")
        self.assertNotIn("prediction",result);self.assertIn("segmentation",result);self.assertIn("comparison",result)
        self.assertEqual(events,["inference","comparison"])
        self.assertTrue(result["segmentation"]["mask_media"].startswith("research-output/"+result["id"]+"/"))


if __name__=="__main__":
    unittest.main()
