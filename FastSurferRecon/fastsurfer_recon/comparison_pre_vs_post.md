# Comparison: Pre-conversion vs Post-conversion Commands (Stages before s14)

## FastSurfer Stage Reference
- **s05**: norm_t1 - Create norm.mgz and T1.mgz
- **s07**: wm_filled - WM segmentation and filled volume
- **s08**: tessellation - Surface tessellation (orig.nofix)
- **s09**: smoothing - Surface smoothing (smoothwm.nofix)
- **s10**: inflation - Surface inflation (inflate1)
- **s11**: spherical_projection - Spherical projection (qsphere)
- **s12**: topology_fix - Topology fix (fix)
- **s13**: white_preaparc - White preaparc surface
- **s14**: parcellation - Cortical parcellation mapping
- **s15**: surface_placement - White and pial surface placement

---

## Key Differences Found (with FastSurfer Stage Mapping)

### 1. **mri_normalize** (Intensity Normalization) - **s07** (wm_filled)

**Pre-conversion:**
```bash
mri_normalize -seed 1234 -mprage -noconform -aseg aseg.presurf.mgz -mask brainmask.mgz norm.mgz brain.mgz
```

**Post-conversion:**
```bash
mri_normalize -g 1 -seed 1234 -mprage -noconform -aseg mri/aseg.presurf.mgz -mask mri/brainmask.mgz mri/norm.mgz mri/brain.mgz
```

**Differences:**
- Post has `-g 1` flag (gradient flag)
- Post uses `mri/norm.mgz` as INPUT (instead of `norm.mgz` as output)
- Post uses full paths with `mri/` prefix

---

### 2. **mri_mask** (Mask BFS) - **s07** (wm_filled)

**Pre-conversion:**
```bash
mri_mask -T 5 brain.mgz brainmask.mgz brain.finalsurfs.mgz
```

**Post-conversion:**
```bash
mri_mask -T 5.0 mri/brain.mgz mri/brainmask.mgz mri/brain.finalsurfs.mgz
```

**Differences:**
- Post uses `5.0` instead of `5` (minor, likely same behavior)
- Post uses full paths with `mri/` prefix

---

### 3. **mri_fill** (Fill) - **s07** (wm_filled)

**Pre-conversion:**
```bash
mri_fill -a ../scripts/ponscc.cut.log -segmentation aseg.presurf.mgz -ctab /usr/local/freesurfer/7.4.1/SubCorticalMassLUT.txt wm.mgz filled.mgz
```

**Post-conversion:**
```bash
mri_fill -segmentation mri/aseg.presurf.mgz -ctab /usr/local/freesurfer/7.4.1/SubCorticalMassLUT.txt mri/wm.mgz mri/filled.mgz
```

**Differences:**
- **CRITICAL**: Post is **MISSING** the `-a ../scripts/ponscc.cut.log` flag
- This flag specifies the pons/CC cut log file, which is important for proper segmentation
- Post uses full paths with `mri/` prefix

---

### 4. **mri_pretess** (New in Post) - **s08** (tessellation)

**Pre-conversion:**
- Not present

**Post-conversion:**
```bash
mri_pretess mri/filled.mgz 255 mri/brainmask.mgz mri/filled-pretess255.mgz
mri_pretess mri/filled.mgz 127 mri/brainmask.mgz mri/filled-pretess127.mgz
```

**Differences:**
- Post has explicit pretess steps that were likely embedded in recon-all before

---

### 5. **mri_mc** (Marching Cubes - New in Post) - **s08** (tessellation)

**Pre-conversion:**
- Not present (likely embedded in recon-all)

**Post-conversion:**
```bash
mri_mc mri/filled-pretess255.mgz 255 surf/lh.orig.nofix.predec
mri_mc mri/filled-pretess127.mgz 127 surf/rh.orig.nofix.predec
```

**Differences:**
- Post explicitly calls marching cubes to generate initial surfaces

---

### 6. **mris_extract_main_component** (New in Post) - **s08** (tessellation)

**Pre-conversion:**
- Not present

**Post-conversion:**
```bash
mris_extract_main_component .../lh.orig.nofix.predec .../lh.orig.nofix.predec
mris_extract_main_component .../rh.orig.nofix.predec .../rh.orig.nofix.predec
```

**Differences:**
- Post explicitly extracts main component

---

### 7. **mris_remesh** (After fix_topology) - **s12** (topology_fix)

**Pre-conversion:**
```bash
mris_remesh --remesh --iters 3 --input .../rh.orig.premesh --output .../rh.orig
```

**Post-conversion:**
```bash
mris_remesh --desired-face-area 1.0 --input .../rh.orig.premesh --output .../rh.orig
```

**Differences:**
- Pre uses `--remesh --iters 3`
- Post uses `--desired-face-area 1.0`
- **Different remeshing strategies!**

---

### 8. **mris_smooth** (Initial smoothing) - **s09** (smoothing)

**Pre-conversion:**
- Not explicitly shown (likely embedded in recon-all stages)

**Post-conversion:**
```bash
mris_smooth -n 2 -nw -seed 1234 .../lh.orig.nofix .../lh.smoothwm.nofix
mris_smooth -n 2 -nw -seed 1234 .../rh.orig.nofix .../rh.smoothwm.nofix
```

**Differences:**
- Post explicitly shows smoothing with `-n 2` iterations

---

### 9. **mris_smooth** (After white.preaparc - Smooth2) - **Embedded in recon-all** (not a separate FastSurfer stage)

**Pre-conversion:**
```bash
mris_smooth -n 3 -nw -seed 1234 ../surf/rh.white.preaparc ../surf/rh.smoothwm
mris_smooth -n 3 -nw -seed 1234 ../surf/lh.white.preaparc ../surf/lh.smoothwm
```

**Post-conversion:**
- Not explicitly shown (likely embedded in recon-all `-smooth2`)

**Differences:**
- Pre uses `-n 3` iterations
- Post uses recon-all `-smooth2` flag (which may use different parameters)

---

### 10. **mris_curvature** (Curvature computation) - **Embedded in recon-all** (replaced by s15 in post)

**Pre-conversion:**
```bash
mris_curvature -w -seed 1234 rh.white.preaparc
mris_curvature -seed 1234 -thresh .999 -n -a 5 -w -distances 10 10 rh.inflated
```

**Post-conversion:**
- Not present (replaced by `mris_place_surface --curv-map`)

**Differences:**
- Pre uses `mris_curvature` command
- Post uses `mris_place_surface --curv-map` (different method)

---

### 11. **mris_place_surface** (White surface placement) - **s13** (white_preaparc) and **s15** (surface_placement)

**Pre-conversion:**
```bash
mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --wm wm.mgz --threads 12 --invol brain.finalsurfs.mgz --rh --i ../surf/rh.orig --o ../surf/rh.white.preaparc --white --seg aseg.presurf.mgz --nsmooth 5
```

**Post-conversion:**
```bash
mris_place_surface --adgws-in .../autodet.gw.stats.rh.dat --seg .../aseg.presurf.mgz --threads 12 --wm .../wm.mgz --invol .../brain.finalsurfs.mgz --rh --o .../rh.white --white --rip-label .../rh.cortex.label --rip-bg --rip-surf .../rh.white.preaparc --aparc .../rh.aparc.ARM2atlas.mapped.annot --i .../rh.white.preaparc
```

**Differences:**
- Post has additional flags: `--rip-label`, `--rip-bg`, `--rip-surf`, `--aparc`
- Post uses `--i .../rh.white.preaparc` (input surface) vs Pre uses `--i ../surf/rh.orig`
- Post outputs to `rh.white` directly, not `rh.white.preaparc`
- Pre has `--nsmooth 5`, Post doesn't show this explicitly

---

### 12. **mris_autodet_gwstats** (AutoDetGWStats) - **s13** (white_preaparc)

**Pre-conversion:**
```bash
mris_autodet_gwstats --o ../surf/autodet.gw.stats.rh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/rh.orig.premesh
```

**Post-conversion:**
- Embedded in `recon-all -hemi rh -autodetgwstats`

**Differences:**
- Pre shows explicit command
- Post uses recon-all wrapper

---

### 13. **mris_remesh** (Initial remeshing before fix_topology) - **s08** (tessellation)

**Pre-conversion:**
- Not shown (likely embedded)

**Post-conversion:**
```bash
mris_remesh --desired-face-area 0.5 --input .../lh.orig.nofix.predec --output .../lh.orig.nofix
```

**Differences:**
- Post explicitly remeshes with `--desired-face-area 0.5` before topology fixing

---

## Summary of Critical Differences by FastSurfer Stage

### s05 (norm_t1) - Create norm.mgz and T1.mgz
- **Note**: This stage creates norm.mgz, but the mri_normalize differences are in s07

### s07 (wm_filled) - WM segmentation and filled volume
1. **mri_normalize**: Post adds `-g 1` flag and uses `mri/norm.mgz` as input instead of output
2. **mri_mask**: Minor difference (`-T 5` vs `-T 5.0`)
3. **mri_fill**: **CRITICAL** - Post is missing `-a ../scripts/ponscc.cut.log` flag (pons/CC cut log)

### s08 (tessellation) - Surface tessellation
4. **mri_pretess**: Post explicitly shows pretess steps (new in post)
5. **mri_mc**: Post explicitly shows marching cubes (new in post)
6. **mris_extract_main_component**: Post explicitly extracts main component (new in post)
7. **mris_remesh (initial)**: Post uses `--desired-face-area 0.5` (new explicit step for hires)

### s09 (smoothing) - Surface smoothing
8. **mris_smooth**: Post explicitly shows smoothing with `-n 2` iterations

### s10 (inflation) - Surface inflation
- No differences found (both use mris_inflate with similar parameters)

### s12 (topology_fix) - Topology fix
9. **mris_remesh (after fix)**: **CRITICAL** - Pre uses `--remesh --iters 3`, Post uses `--desired-face-area 1.0` (different remeshing strategy)

### s13 (white_preaparc) - White preaparc surface
10. **mris_autodet_gwstats**: Pre shows explicit command, Post uses recon-all wrapper
11. **mris_place_surface (white.preaparc)**: Pre uses `--i ../surf/rh.orig --o ../surf/rh.white.preaparc --nsmooth 5`, Post uses different input and additional flags

### s15 (surface_placement) - White and pial surface placement
12. **mris_place_surface (white)**: Post has additional flags (`--rip-label`, `--rip-bg`, `--rip-surf`, `--aparc`) and uses `white.preaparc` as input instead of `orig`
13. **mris_curvature vs mris_place_surface --curv-map**: **CRITICAL** - Pre uses `mris_curvature` command, Post uses `mris_place_surface --curv-map` (different method)

### Embedded in recon-all (Smooth2/Inflate2/Curvature)
14. **mris_smooth (smooth2)**: Pre uses `-n 3` iterations explicitly, Post uses recon-all `-smooth2` wrapper
15. **mris_curvature**: Pre uses `mris_curvature` command, Post uses `mris_place_surface --curv-map` in s15

---

## Most Critical Differences (Likely to Affect Results)

1. **s07**: Missing pons/CC cut log in `mri_fill` (`-a ../scripts/ponscc.cut.log`) - **HIGH IMPACT**
2. **s12**: Different remeshing strategy (`--remesh --iters 3` vs `--desired-face-area 1.0`) - **HIGH IMPACT**
3. **s15**: Different curvature computation method (`mris_curvature` vs `mris_place_surface --curv-map`) - **MEDIUM IMPACT**
4. **s07**: `mri_normalize` input/output difference with `-g 1` flag - **MEDIUM IMPACT**
5. **s13/s15**: White surface placement differences (additional flags, different inputs) - **MEDIUM IMPACT**

