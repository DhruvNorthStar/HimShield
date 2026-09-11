# Working together with git

This is the one workflow the three of us use. It is called GitHub Flow and has one rule: **`main` always works, and nobody commits to it directly.** Every piece of work happens on a short branch, goes through a pull request, and a teammate glances at it before it is merged.

Why this one: it is the simplest workflow that still protects `main`. Heavier models such as git-flow add `develop` and `release` branches, which a three-person, one-semester project does not need. Pushing straight to `main` is simpler still, but then one broken commit breaks everyone's afternoon.

## One-time setup

One person (the repo owner):

1. On github.com, create a **private** repository named `landslide-uttarakhand`. Do not add a README or .gitignore there; we already have them.
2. Settings > Collaborators > add the other two by GitHub username.
3. Settings > Branches > Add rule for `main` > tick "Require a pull request before merging". This makes the rule above enforced, not just agreed.
4. Push the existing repo:
   ```
   git remote add origin https://github.com/<owner>/landslide-uttarakhand.git
   git push -u origin main
   ```

Everyone else:

```
cd C:\Projects
git clone https://github.com/<owner>/landslide-uttarakhand.git
cd landslide-uttarakhand
git config user.name "Your Name"
git config user.email "you@example.com"
conda activate landslide
nbstripout --install
```

## The daily loop

```
git switch main
git pull                              # get everyone's merged work
git switch -c yourname/short-topic    # e.g. riya/eda-heatmap
# ... work, then save progress as often as you like:
git add src/preprocess.py
git commit -m "Add VIF loop with drop logging"
git push -u origin yourname/short-topic
```

Then on GitHub, open a pull request into `main`. A teammate reads it, and whoever opened it clicks "Merge". Delete the branch afterwards.

Keep branches short: one to three days. The longer a branch lives, the more it drifts from `main` and the worse the merge. If `main` moved while you worked, bring it in before opening the PR:

```
git switch main
git pull
git switch yourname/short-topic
git merge main
```

Use `git add <specific files>` rather than `git add .` so you do not commit something by accident.

## Why data and models never go in git

- **Size.** One 30 m raster covering Uttarakhand is roughly 250 to 500 MB uncompressed, and we produce around eight of them (DEM, slope, aspect, curvature, three distance rasters, rainfall). GitHub rejects any file over 100 MB and asks that a whole repo stay under about 1 GB.
- **Git never forgets.** Deleting a big file in a later commit does not shrink the repo. The file stays in history and every clone downloads it forever. Removing it means rewriting history, which is painful with three people.
- **They are regenerable.** Raw data comes from the portals, and models come from running the scripts. What we version is the code and instructions that produce them.
- **Pickled models are fragile and unsafe to share.** A `.pkl` is tied to the scikit-learn version that made it, and loading one runs code, so only load pickles you built yourselves.

The one exception is `data/processed/*.csv`, which is a few hundred KB.

To share data files: keep one shared Google Drive (or OneDrive) folder that mirrors `data/raw/` and `data/shapefiles/`. Each person copies the files into their local clone.

If you accidentally commit a large file and have **not pushed yet**:

```
git rm --cached path/to/bigfile.tif
git commit --amend --no-edit
```

If it is already pushed, stop and tell the team before doing anything else.

## Notebooks: the conflict you will hit

A `.ipynb` file is JSON. Besides your code it stores cell outputs, execution counts and plots as long base64 strings. If two people run the same notebook, those parts differ on every line, and git reports a conflict even when nobody changed the code.

Three habits prevent almost all of it:

1. **One owner per notebook.** `01_eda.ipynb` has one owner and `02_model_comparison.ipynb` has one owner. Others suggest changes through the owner, or in their own scratch notebook, which they do not commit.
2. **Logic lives in `src/*.py`; notebooks only call it.** Python files merge cleanly line by line. A notebook cell should look like `from src.preprocess import run_preprocessing`, not 80 lines of code.
3. **nbstripout** (installed during setup) removes outputs at commit time, so the noisy parts never reach git.

If a notebook conflicts anyway, **do not edit the conflict markers by hand.** A notebook with `<<<<<<<` inside is invalid JSON and will not open. Instead, keep one whole version and add the other person's cells back manually:

```
# while merging main into your branch:
git checkout --theirs notebooks/01_eda.ipynb   # keep main's version
#   or
git checkout --ours notebooks/01_eda.ipynb     # keep your branch's version

# open the notebook, paste in the cells from the version you did not keep, save
git add notebooks/01_eda.ipynb
git commit
```

During `git merge main`, "ours" is your branch and "theirs" is `main`. (During a rebase they swap, which is one reason we merge rather than rebase.) To see what the other version contained, run `git show main:notebooks/01_eda.ipynb > other_version.ipynb` and open that file side by side. Delete it afterwards.

## Commit messages

Say what the commit does, in the imperative: "Add distance-to-faults column", "Fix SMOTE applied before split". Messages like "update", "changes" or "final final" do not help anyone later.
