"""Meaningful regressions for the chat attachment boundary (synthetic fixtures)."""
from pathlib import Path
import unittest
from unittest import mock
from cancer_workbench.research import attachments
from cancer_workbench.app import api
from cancer_workbench.coordinator import ChatResult, ScriptedProvider, ToolBox, run_turn


class ChatAttachmentTests(unittest.TestCase):
    def test_reference_labels_and_filename_are_not_added_to_model_context(self):
        meta={"id":"a"*64,"format":"image","original_name":"known-malignant-answer.png","label":"secret-reference"}
        model={"formats":["image"],"backend":"pixels","preprocessing":{"mode":"L"},
               "id":"fixture","task":"classification","modality":"ultrasound","anatomy":"breast"}
        with mock.patch.object(attachments.runtime,"resolve_input",return_value=(Path("fixture.png"),meta)), \
             mock.patch.object(attachments.runtime,"profile",return_value=(Path("fixture"),model)), \
             mock.patch.object(attachments.runtime,"pixels") as transform:
            context=attachments.context([{"input_id":"a"*64,"workflow_id":"fixture"}])
        self.assertIn("input_id "+"a"*64,context)
        self.assertNotIn("known-malignant",context)
        self.assertNotIn("secret-reference",context)
        transform.assert_called_once_with(Path("fixture.png"),model["preprocessing"])

    def test_reference_injection_and_path_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            attachments.context([{"input_id":"a"*64,"label":"malignant"}])
        with self.assertRaises(ValueError):
            attachments.context([{"input_id":"../../private"}])

    def test_mismatched_workflow_format_is_rejected_before_model_call(self):
        with mock.patch.object(attachments.runtime,"resolve_input",return_value=(Path("volume.nii.gz"),{"id":"a"*64,"format":"nifti"})), \
             mock.patch.object(attachments.runtime,"profile",return_value=(Path("fixture"),{"formats":["image"]})):
            with self.assertRaisesRegex(ValueError,"does not accept"):
                attachments.context([{"input_id":"a"*64,"workflow_id":"fixture"}])

    def test_attachment_context_is_never_sent_to_remote_llm(self):
        provider=ScriptedProvider([],profile="test");provider.base_url="https://remote.invalid/v1";provider.model="test"
        with mock.patch.object(api,"attachment_context",return_value="fixture attachment"), \
             mock.patch.object(api.research,"tool_registration",return_value=([],{})), \
             mock.patch.object(api,"make_provider",return_value=provider):
            result=api.ask({"question":"Analyze","profiles":["test"],"attachments":[{"input_id":"a"*64}]})
        self.assertIn("on this PC",result["results"][0]["error"])
        self.assertEqual(provider.calls,[])

    def test_output_limit_is_reported_as_incomplete(self):
        provider=ScriptedProvider([ChatResult("cut off",[],"length","test","test")])
        result=run_turn(provider,ToolBox([]),"fixture")
        self.assertEqual(result.stopped,"response_limit")
        self.assertEqual(result.steps[0]["finish_reason"],"length")


if __name__=="__main__":
    unittest.main()
