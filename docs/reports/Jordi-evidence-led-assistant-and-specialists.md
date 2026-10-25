# OncoloHealth measured accuracy and execution scoreboard

Recorded held-out sample-level tests are separate from successful tool execution and agreement on selected demonstration inputs. These are already-inspected research comparisons; missing patient/lesion/slide identities prevent a patient-independent clinical accuracy claim.

| Specialist | Test n | Accuracy | Balanced accuracy | AUROC | Evaluation scope |
|---|---:|---:|---:|---:|---|
| breastmnist-pixel-baseline | 156 | 0.763 | 0.732 | 0.833 | local_sample_level_test |
| breastmnist-resnet50-research | 156 | 0.776 | 0.741 | 0.830 | local_sample_level_test |
| btxrd-resnet50-three-class | 62 | 0.629 | 0.627 | 0.785 | local_sample_level_test |
| dermamnist-pixel-baseline | 2005 | 0.515 | 0.497 | 0.838 | local_sample_level_test |
| dermamnist-resnet50-research | 2005 | 0.592 | 0.531 | 0.866 | local_sample_level_test |
| monai-brats-segresnet-local | — | — | — | — | potentially_overlapping_demonstration |
| monai-lung-retinanet-local | — | — | — | — | publisher_validation_demonstration |
| nodulemnist3d-pixel-baseline | 310 | 0.816 | 0.786 | 0.853 | local_sample_level_test |
| pathmnist-pixel-baseline | 7180 | 0.510 | 0.431 | 0.876 | local_sample_level_test |
| pathmnist-resnet50-research | 7180 | 0.808 | 0.756 | 0.960 | local_sample_level_test |

## What changed

- Pathology: frozen ResNet features plus a fitted head reached 80.8% accuracy versus 51.0% for the pixel baseline on the same 7,180 already-inspected test patches. Macro AUROC 0.960 versus 0.876.
- Skin: 59.2% accuracy versus 51.5% on 2,005 already-inspected test images; macro AUROC 0.866 versus 0.838. This is still a modest research model, not a phone-photo classifier.
- Ultrasound: 77.6% versus 76.3% accuracy on 156 test images, but AUROC 0.830 versus 0.833 and malignant sensitivity unchanged at 66.7%. This is a complementary comparison, not a uniform improvement.
- All original specialists remain installed. New heads reuse the same frozen publisher weights and source splits, preserve RGB for skin/pathology and replicate ultrasound grayscale. They are still restricted to 28-pixel dataset-style inputs.
- The first report attempt failed due to a metrics-code bug. Existing heads and measured source-bound feature caches were recovered without retraining; fresh-process and actual-app comparisons pass. Prior failure reports remain intact.
- MRI and full CT are overlap/publisher-validation demonstrations with no claimed independent test accuracy. Dice/box agreement for one case must not be put into an accuracy column.

## App execution and selected-reference comparisons

```json
{
  "execution": {
    "attempts": 60,
    "completed": 53,
    "failed": 7,
    "refused": 0,
    "other_status": 0,
    "synthetic_excluded": 0,
    "unmatched_model_records": 0
  },
  "reference_agreement": {
    "classification_compared": 37,
    "classification_matched": 24,
    "classification_disagreed": 13,
    "segmentation_compared": 6,
    "detection_compared": 4,
    "meaning": "Selected-input reference agreement is separate from test-set accuracy and may include repeated, validation or overlapping cases."
  },
  "recent_failures": [
    {
      "observation_id": "5dfe1ff518824a32ac4485a0b8260ad5",
      "status": "failed",
      "error": "ValueError: Input bytes changed after upload; upload the reviewed file again."
    },
    {
      "observation_id": "6cd2342241df42599fc2aae31f2ff3d7",
      "status": "failed",
      "error": "ValueError: This input is a known training source and is refused for live scoring."
    },
    {
      "observation_id": "be9ac34a2bda47a59bafbd7787a9d89a",
      "status": "failed",
      "error": "ValueError: Incompatible input format; this model requires: nifti"
    },
    {
      "observation_id": "edc0c2edd2994f3cbf54d333333b0417",
      "status": "failed",
      "error": "ValueError: This input is a known training source and is refused for live scoring."
    },
    {
      "observation_id": "fb3d8a036df14c4880e596c396588688",
      "status": "failed",
      "error": "ValueError: MRI inference implementation differs from its verified manifest."
    }
  ],
  "denominator_note": "Execution attempts count saved observation IDs, not patients or independent test examples. Recorded failed refusals stay failed; refusal counts require an explicit rejected/refused status."
}
```

Each saved observation ID counts an attempt; repeated requests are not new test patients. Failed runs, catalog refusal, unavailable models and training-input refusals remain visible. Historical refusal receipts saved with failed status are not retroactively relabeled.

## Professional assistance

The actual local main3 now leads with model findings, measured basis and appropriate uncertainty rather than blanket refusal. It can report malignant/benign task labels, explain the test denominator and sensitivity, and discuss evidence. It does not invent lesion morphology or convert a class score into calibrated disease probability. This is changed guidance/tool evidence, not a newly trained Gemma adapter.

Evidence: C:\Users\Jordi nieves\Documents\OncoloHealth-professional-assistance-live-verification.json and C:\Users\Jordi nieves\Documents\OncoloHealth-neural-app-live-verification.json.
