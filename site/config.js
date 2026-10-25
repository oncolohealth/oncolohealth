// Site settings. Edit these when deploying.
window.ONCOLO_SITE = {
  // How the contribute form delivers a submission:
  //   "download" - the contributor downloads the submission file and emails it to contactEmail
  //   "github"   - opens a prefilled issue on githubRepo (the repository must be public)
  //   "endpoint" - POSTs the submission JSON to endpoint (a form backend such as Formspree)
  submitMode: "download",
  contactEmail: "",
  githubRepo: "oncolohealth/oncolohealth",
  endpoint: ""
};
