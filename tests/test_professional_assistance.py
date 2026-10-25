"""Refresh old chats and expose actual evidence without rerunning specialist inference."""
import copy,json,unittest
from unittest import mock
from cancer_workbench.app import api
from cancer_workbench.app.assistant import guided_history
from cancer_workbench.coordinator import ChatResult,ScriptedProvider,ToolCall
from cancer_workbench.coordinator.loop import SYSTEM_PROMPT,LEGACY_SYSTEM_PROMPT

class ProfessionalAssistanceTests(unittest.TestCase):
    def test_saved_app_policy_refreshes_but_custom_system_and_conversation_stay_intact(self):
        history=[{'role':'system','content':LEGACY_SYSTEM_PROMPT+'\n\nCurrent workbench interface:\nold instructions'},
                 {'role':'user','content':'Explain the observed result'},
                 {'role':'assistant','content':'Earlier unnecessarily broad refusal'}]
        before=copy.deepcopy(history)
        refreshed=guided_history(history,specialists=[{'id':'fixture','summary':'synthetic specialist'}])
        self.assertTrue(refreshed[0]['content'].startswith(SYSTEM_PROMPT))
        self.assertEqual(refreshed[1:],history[1:]);self.assertEqual(history,before)
        custom=guided_history([{'role':'system','content':'Custom institutional instructions'}])
        self.assertTrue(custom[0]['content'].startswith('Custom institutional instructions'))

    def test_evidence_tool_runs_without_predict_or_reference_access(self):
        evidence={'model_id':'fixture','evaluation':{'n':156,'metrics':{'accuracy':119/156}}}
        provider=ScriptedProvider([ChatResult(None,[ToolCall('e1','get_specialist_evidence',json.dumps({'model_id':'fixture'}))],'tool_calls','test','test'),
                                   ChatResult('119 of156 on the saved test split.',[],'stop','test','test')],profile='test')
        provider.model='test'
        with mock.patch.object(api,'make_provider',return_value=provider), \
             mock.patch.object(api.research,'tool_registration',return_value=([{'id':'fixture','summary':'test'}],{})), \
             mock.patch.object(api.research,'specialist_evidence',return_value=evidence) as read, \
             mock.patch.object(api.research,'predict') as predict:
            result=api.ask({'question':'What was its measured accuracy?','profiles':['test']})['results'][0]
        read.assert_called_once_with(model_id='fixture');predict.assert_not_called()
        observed=result['steps'][0]['tool_calls'][0]['observed']
        self.assertEqual(observed['result']['evaluation']['n'],156)
        self.assertEqual(result['stopped'],'answered')

if __name__=='__main__':unittest.main()
