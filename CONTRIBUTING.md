# Working with this repository

Landslide Susceptibility Mapping for Uttarakhand is built by one person, so the workflow is deliberately simple: **commit on `main`, push after every commit.** GitHub then always holds the latest working state, and a lost laptop costs nothing but time.

Repository: https://github.com/DhruvNorthStar/HimShield. It is **public**, so anything committed, including the author name and email on every commit, can be read by anyone.

## The daily loop

```
git status                    # what changed? check nothing large or private is listed
git add src/preprocess.py     # name the files, rather than `git add .`
git commit -m "Add VIF loop with drop logging"
git push
```

Naming files keeps a stray raster or a scratch notebook out of a commit. Run `git status` before every commit and read the list.

**When a branch is worth it:** only for a risky experiment you may throw away, such as trying a different model or restructuring a script. Work on `git switch -c try/new-idea`, and when it works, `git switch main` then `git merge try/new-idea` and push. If it does not work, switch back to `main` and delete the branch; `main` never saw it.

## Setting up a second machine

```
git clone https://github.com/DhruvNorthStar/HimShield.git
cd HimShield
conda env create -f environment.lock.yml
conda activate landslide
nbstripout --install
python verify_setup.py
```

The clone contains code, docs, the synthetic dataset and figures, but no raw data, rasters or models. Rebuild those with `docs/01_data_sourcing.md` and `docs/02_qgis_processing.md`. On both machines, run `git pull` before starting work, so the two copies never drift apart.

## Why data and models never go in git

- **Size.** One 30 m raster covering Uttarakhand is 225 to 450 MB uncompressed, and the project builds about ten. GitHub rejects any file over 100 MB and asks that a whole repository stay under about 1 GB.
- **Git never forgets.** Deleting a big file in a later commit does not shrink the repository. The file stays in history and every clone downloads it forever. Removing it means rewriting published history.
- **They are regenerable.** Raw data comes from the portals, and models come from running the scripts. What gets versioned is the code and the instructions that produce them.
- **Licences.** Several sources carry licences (OpenStreetMap ODbL, GEM faults CC BY-SA, geoBoundaries ODbL) that a public copy would have to honour. Keeping derived layers out of the repository avoids that.
- **Pickled models are fragile and unsafe to share.** A `.pkl` is tied to the scikit-learn version that made it, and loading one runs code, so only load pickles you built yourself.

`.gitignore` enforces all of this. What stays tracked on purpose: `data/processed/dataset_synthetic.csv`, the QuickOSM extent rectangles in `data/processed/quickosm_extents/`, the figures in `outputs/`, and the QGIS project `uttarakhand.qgz`.

If you accidentally commit a large or private file and have **not pushed yet**:

```
git rm --cached path/to/bigfile.tif
git commit --amend --no-edit
```

If it is already pushed, stop. Removing it properly means rewriting history on GitHub, which needs care.

## Notebooks

A `.ipynb` file is JSON. Besides the code it stores cell outputs, execution counts and plots as long base64 strings, so running a notebook changes the file even when no code changed. Two habits keep that harmless:

1. **Logic lives in `src/*.py`; notebooks only call it.** A notebook cell should look like `from src import eda`, not 80 lines of code.
2. **nbstripout** (installed during setup) removes outputs at commit time, so the noisy parts never reach git.

Conflicts can still happen if the same notebook is edited on two machines, or on GitHub and locally. **Do not edit the conflict markers by hand**: a notebook with `<<<<<<<` inside is invalid JSON and will not open. Keep one whole version and copy the missing cells across:

```
git checkout --ours notebooks/01_eda.ipynb     # keep your local version
#   or
git checkout --theirs notebooks/01_eda.ipynb   # keep the incoming version
# open the notebook, paste in the cells from the version you did not keep, save
git add notebooks/01_eda.ipynb
git commit
```

To see the other version first, run `git show origin/main:notebooks/01_eda.ipynb > other_version.ipynb`, open it side by side, and delete it afterwards.

## Commit messages

Say what the commit does, in the imperative: "Add distance-to-faults column", "Fix SMOTE applied before split". Add a short body when the reason is not obvious from the change itself. Messages like "update", "changes" or "final final" do not help anyone later, including you in a viva.
