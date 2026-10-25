import unittest
from cancer_workbench.research.evidence import compare_reports

def report(mid,accuracy,auc):
 return {'model_id':mid,'evaluation':{'scope':'local_sample_level_test','dataset':'synthetic','n':156,
 'metrics':{'accuracy':accuracy,'roc_auc':auc},'per_class':{'malignant':{'recall':2/3}}}}

class SpecialistComparisonTests(unittest.TestCase):
 def test_higher_accuracy_can_coexist_with_lower_auroc_and_equal_recall(self):
  r=compare_reports([report('old',119/156,.833),report('new',121/156,.830)],same_test_inputs=True)
  d=r['differences_vs_first'][0]
  self.assertTrue(r['comparable_same_source_test'])
  self.assertAlmostEqual(d['metric_difference']['accuracy'],2/156)
  self.assertAlmostEqual(d['metric_difference']['roc_auc'],-.003)
  self.assertEqual(d['per_class_recall_difference']['malignant'],0)
 def test_no_comparative_delta_without_verified_same_test_membership(self):
  r=compare_reports([report('old',.7,.8),report('new',.8,.9)])
  self.assertFalse(r['comparable_same_source_test']);self.assertEqual(r['differences_vs_first'][0]['metric_difference'],{})
 def test_different_datasets_or_missing_metric_do_not_manufacture_a_comparison(self):
  a,b=report('old',.7,.8),report('new',.8,.9);b['evaluation']['dataset']='another'
  r=compare_reports([a,b],same_test_inputs=True)
  self.assertFalse(r['comparable_same_source_test'])
  b['evaluation']['dataset']='synthetic';del b['evaluation']['metrics']['roc_auc']
  r=compare_reports([a,b],same_test_inputs=True)
  self.assertNotIn('roc_auc',r['differences_vs_first'][0]['metric_difference'])
 def test_class_definitions_must_match_even_on_the_same_input_files(self):
  a,b=report('old',.7,.8),report('new',.8,.9)
  b['evaluation']['class_order']=['malignant','benign','normal']
  r=compare_reports([a,b],same_test_inputs=True)
  self.assertFalse(r['comparable_same_source_test'])
  self.assertEqual(r['differences_vs_first'][0]['metric_difference'],{})

if __name__=='__main__':unittest.main()
