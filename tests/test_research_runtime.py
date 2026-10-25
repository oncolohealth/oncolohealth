"""Input/reference isolation and observed-result regressions; fixtures are synthetic."""
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cancer_workbench.research import runtime as rt


class ResearchRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, path in {"INPUTS": root/"inputs", "REFERENCES": root/"references",
                           "RESULTS": root/"observations", "ARTIFACTS": root/"models", "DATA_DIR": root/"data"}.items():
            patch = mock.patch.object(rt,name,path); patch.start(); self.addCleanup(patch.stop)

    def add_input(self):
        from PIL import Image
        buffer = io.BytesIO(); Image.new("L",(28,28),color=80).save(buffer,format="PNG")
        with mock.patch("cancer_workbench.acquisition.budget.check",return_value=(True,{})):
            return rt.upload({"name":"neutral.png","data":base64.b64encode(buffer.getvalue()).decode()})

    def add_model(self):
        import numpy as np
        from cancer_workbench.learning.heads import HeadModel, _LinearProbs, head_fingerprint, save_head
        model_id="synthetic-fixture"
        folder=rt.ARTIFACTS/model_id; folder.mkdir(parents=True)
        head=HeadModel(encoder={"encoder_id":"pixels-fixture","revision":"test","preprocessing_hash":"test"},
            classes=["a","b"],C=1.,val_score=.5,mean=np.zeros(784),scale=np.ones(784),
            clf=_LinearProbs(np.zeros((1,784)),np.array([0.])),train_ids=frozenset(),train_patients=frozenset())
        save_head(head,folder/"head.npz")
        manifest={"id":model_id,"state":"verified","backend":"pixels","formats":["image"],"classes":["a","b"],
                  "training":{"synthetic_fixture":True},"preprocessing":{"kind":"image","mode":"L"},
                  "head_fingerprint":head_fingerprint(head),"output_meaning":"fixture only","limitations":["synthetic"],
                  "files":{"head.npz":rt.sha_file(folder/"head.npz")}}
        rt._save(folder/"manifest.json",manifest)
        return model_id,folder

    def test_reference_never_changes_prediction_or_input_listing(self):
        meta=self.add_input(); model_id,_=self.add_model()
        first=rt.predict(model_id,meta["id"])
        self.assertEqual(first["status"],"ok")
        self.assertNotIn("comparison",first)
        rt.set_reference({"input_id":meta["id"],"model_id":model_id,"label":"b","source":"synthetic answer key"})
        second=rt.predict(model_id,meta["id"])
        self.assertEqual(first["prediction"],second["prediction"])
        self.assertEqual(second["comparison"]["reference"]["label"],"b")
        self.assertNotIn("reference",json.dumps(rt.list_inputs()))
        self.assertEqual(len(list(rt.RESULTS.glob("*.json"))),2)

    def test_modified_input_is_refused_and_failure_is_saved(self):
        meta=self.add_input(); model_id,_=self.add_model()
        path,_=rt.resolve_input(meta["id"]); path.write_bytes(b"changed")
        result=rt.predict(model_id,meta["id"])
        self.assertEqual(result["status"],"failed")
        self.assertIn("changed after upload",result["error"])
        self.assertTrue((rt.RESULTS/(result["id"]+".json")).is_file())

    def test_missing_or_modified_artifact_never_predicts(self):
        meta=self.add_input(); model_id,folder=self.add_model()
        (folder/"head.npz").write_bytes(b"changed")
        result=rt.predict(model_id,meta["id"])
        self.assertEqual(result["status"],"failed")
        self.assertNotIn("prediction",result)

    def test_adapter_rejects_paths_and_injected_reference_inputs(self):
        adapter=rt.ResearchAdapter("fixture")
        self.assertTrue(adapter.validate({"input_id":"../secret"}))
        self.assertTrue(adapter.validate({"input_id":"0"*64,"label":"a"}))

    def test_untrained_full_size_image_is_rejected_by_patch_baseline(self):
        from PIL import Image
        path=Path(self.temp.name)/"full.png"; Image.new("RGB",(100,100)).save(path)
        with self.assertRaisesRegex(ValueError,"28×28"):
            rt.pixels(path,{"kind":"image","mode":"RGB"})

    def test_volume_patch_checks_shape_and_scale(self):
        import nibabel as nib
        import numpy as np
        path=Path(self.temp.name)/"volume.nii.gz"
        nib.save(nib.Nifti1Image(np.zeros((28,28,28),dtype=np.uint8),None),path)
        self.assertEqual(rt.inspect_file(path,".nii.gz")["shape"],[28,28,28])
        self.assertEqual(rt.pixels(path,{"kind":"volume-patch"}).shape,(1,2744))
        nib.save(nib.Nifti1Image(np.zeros((32,32,32),dtype=np.uint8),None),path)
        with self.assertRaisesRegex(ValueError,"not an entire CT"):
            rt.pixels(path,{"kind":"volume-patch"})

    def test_malformed_profile_or_archive_is_not_registered(self):
        with mock.patch("cancer_workbench.acquisition.budget.check",return_value=(True,{})):
            with self.assertRaises(ValueError):
                rt.upload({"name":"profile.csv","data":base64.b64encode(b"a,a\n1,2\n").decode()})
        self.assertEqual(rt.list_inputs(),[])


if __name__=="__main__":
    unittest.main()
