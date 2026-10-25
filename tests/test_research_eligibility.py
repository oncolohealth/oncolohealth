"""Concrete local-only and source-overlap regressions; all inputs are synthetic."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cancer_workbench.app import api
from cancer_workbench.coordinator import ChatResult, ScriptedProvider
from cancer_workbench.research import runtime as rt


class LocalEndpointTests(unittest.TestCase):
    def provider(self, url=None):
        p=ScriptedProvider([ChatResult("offline fixture",[],"stop","fixture","test")],profile="fixture")
        p.model="fixture"
        if url is not None:p.base_url=url
        return p

    def ask(self, provider):
        with mock.patch.object(api,"make_provider",return_value=provider), mock.patch.object(api.research,"tool_registration",return_value=([],{})):
            return api.ask({"question":"Run the specialist on stable input 0000000000000000","profiles":["fixture"]})["results"][0]

    def test_external_provider_is_rejected_even_without_attachments(self):
        provider=self.provider("https://api.anthropic.com/v1")
        result=self.ask(provider)
        self.assertIn("endpoint on this PC",result["error"])
        self.assertEqual(provider.calls,[])

    def test_loopback_provider_is_allowed(self):
        provider=self.provider("http://127.0.0.1:8080/v1")
        self.assertEqual(self.ask(provider)["final"],"offline fixture")
        self.assertEqual(len(provider.calls),1)

    def test_offline_fixture_without_endpoint_remains_allowed(self):
        provider=self.provider()
        self.assertEqual(self.ask(provider)["final"],"offline fixture")


class SourceEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_bone_known_source_uses_bytes_not_the_upload_filename(self):
        from cancer_workbench.experiments import explore
        directory=self.root/"runs"/"bone"; (directory/"splits").mkdir(parents=True)
        (directory/"results.json").write_text(json.dumps({"results":[{"id":"fixture","protocol":"guard"}]}),encoding="utf-8")
        image=self.root/"renamed-upload.bin";image.write_bytes(b"synthetic bound source")
        with (directory/"splits"/"guard.csv").open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["sample_id","partition","sha256"]);writer.writeheader()
            writer.writerow({"sample_id":"different-original-name","partition":"train","sha256":rt.sha_file(image)})
        with mock.patch.object(explore,"RUNS_DIR",self.root/"runs"):
            result=rt.evaluation_eligibility(image,{"backend":"btxrd","run":"bone","result":"fixture"},self.root)
        self.assertEqual(result["known_partition"],"train")
        self.assertFalse(result["may_be_used_for_held_out_sample_comparison"])

    def pixel_source(self,partition):
        import numpy as np
        from PIL import Image
        array=np.arange(784,dtype=np.uint8).reshape(28,28)
        path=self.root/"neutral-renamed.png";Image.fromarray(array).save(path,compress_level=0)
        receipt={"selected_pixel_sha256":{partition:[hashlib.sha256(array.tobytes()).hexdigest()]}}
        (self.root/"training-receipt.json").write_text(json.dumps(receipt),encoding="utf-8")
        (self.root/"manifest.json").write_text("{}",encoding="utf-8")
        model={"backend":"pixels","preprocessing":{"kind":"image","mode":"L"},"training":{},"formats":["image"]}
        return path,model

    def test_decoded_training_pixels_are_rejected_before_model_execution_and_recorded(self):
        path,model=self.pixel_source("train")
        meta={"id":"0"*64,"sha256":rt.sha_file(path),"format":"image"}
        with mock.patch.object(rt,"RESULTS",self.root/"observations"), mock.patch.object(rt,"resolve_input",return_value=(path,meta)), mock.patch.object(rt,"profile",return_value=(self.root,model)):
            result=rt.predict("fixture",meta["id"])
        self.assertEqual(result["status"],"failed")
        self.assertEqual(result["evaluation_eligibility"]["known_partition"],"train")
        self.assertIn("known training",result["error"])
        self.assertNotIn("prediction",result)
        self.assertTrue((self.root/"observations"/(result["id"]+".json")).is_file())

    def test_validation_disclosed_test_and_unmatched_have_distinct_eligibility(self):
        path,model=self.pixel_source("val")
        val=rt.evaluation_eligibility(path,model,self.root)
        self.assertEqual(val["known_partition"],"val")
        self.assertIn("optimistic",val["note"])
        self.assertFalse(val["may_be_used_for_held_out_sample_comparison"])
        self.pixel_source("test")
        test=rt.evaluation_eligibility(path,model,self.root)
        self.assertTrue(test["may_be_used_for_held_out_sample_comparison"])
        self.assertFalse(test["independent_patient_evaluation"])
        (self.root/"training-receipt.json").write_text("{}",encoding="utf-8")
        unknown=rt.evaluation_eligibility(path,model,self.root)
        self.assertEqual(unknown["known_partition"],"unknown")
        self.assertFalse(unknown["may_be_used_for_held_out_sample_comparison"])

    def test_compact_tool_result_keeps_evaluation_limit(self):
        result={"status":"ok","id":"observation","evaluation_eligibility":{"known_partition":"val"}}
        with mock.patch.object(rt,"predict",return_value=result):
            output=rt.ResearchAdapter("fixture").run({"input_id":"0"*64})
        self.assertEqual(output["evaluation_eligibility"],result["evaluation_eligibility"])


if __name__=="__main__":unittest.main()
