# Pushing & Releasing

## Everyday push (rolling build)

```bash
git add .
git commit -m "Your message"
git push origin main
```

GitHub Actions builds Windows and Linux binaries automatically and updates the
**"Latest build (main)"** pre-release at:
`https://github.com/<owner>/GDPRScanner/releases/tag/latest`

## Versioned release

Tag the commit and push the tag:

```bash
git tag v1.6.14
git push origin main
git push origin v1.6.14
```

Actions creates a proper GitHub Release named `v1.6.14` with auto-generated
release notes and the built binaries attached.

Append `-beta` or `-rc` to the tag to mark it as a pre-release:

```bash
git tag v1.6.14-beta1
git push origin v1.6.14-beta1
```

## Summary

| Action | Result |
|---|---|
| `git push origin main` | Updates the rolling `latest` pre-release |
| `git push origin v1.x.y` | Creates a new versioned release |
| `git push origin v1.x.y-beta1` | Creates a versioned pre-release |
