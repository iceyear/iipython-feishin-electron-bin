# iipython-feishin-electron-bin

An AUR-style packaging repository for the **iiPythonx** Feishin builds, using the system-wide Electron runtime.

## Local build

```bash
git clone <this-repo-url>
cd iipython-feishin-electron-bin
makepkg -si
```

## Updating

A GitHub Actions workflow is included to keep `PKGBUILD` and `.SRCINFO` in sync with the latest release from
`iiPythonx/feishin`.

- The scheduled cron trigger is **commented out** for now. You can enable it later by uncommenting the `schedule`
  block in `.github/workflows/update-aur.yml`.
- If there is no new upstream release, the workflow exits quickly without rebuilding or creating releases.

If you prefer to update locally, edit `PKGBUILD` and regenerate `.SRCINFO` (or run the update script manually).

```bash
python .github/scripts/update_pkgbuild.py
```
