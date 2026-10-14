# The live descriptions

Back to [how-it-works.md](../how-it-works.md).

Two services show a description of this project that does not live in a file
they read from here. These are their texts, word for word:

| file | where it is shown | format |
|---|---|---|
| `github-about.txt` | the repository's *About* on GitHub | one line |
| `copr-description.md` | COPR project page, *Description* | Markdown |
| `copr-instructions.md` | COPR project page, *Installation Instructions* | Markdown |

`scripts/texts-check.py live` compares each with the live text, on every push to
`main` and every day (check-repo.yml, job `live-texts`). A difference is red
either way round:

- **changed here**: publish it, then the check turns green again:
  - GitHub: `gh repo edit --description "$(cat docs/descriptions/github-about.txt)"`
  - COPR: `copr-cli modify devtools --description "$(cat docs/descriptions/copr-description.md)" --instructions "$(cat docs/descriptions/copr-instructions.md)"`
- **changed on the service** (an edit in a web form): take it into git, or put
  the git text back.

`scripts/texts-check.py live --save DIR` writes the live texts to `DIR`, to
compare them by hand.

`scripts/texts-check.py offline` (part of `scripts/lint.sh`) also makes sure the
COPR texts name every package, and the live check that `CHANGELOG.md` names every
Fedora release COPR builds for.
