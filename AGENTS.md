# EA600 release notes

For every app change shipped as a release, prepend one entry to `siteapp/release_notes.json` in the same change.

- Increase the patch number for a fix or refinement, or increase the minor number and reset the patch number to zero for new functionality.
- Record the date of the release in Europe/London as `YYYY-MM-DD`, a short title and a list of changes written for site administrators.
- Preserve previous entries. Railway supplies the running build revision to Django admin, so the new entry can omit the commit hash.
