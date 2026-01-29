

#---------------------------------
# New invocation of fastsurfer-recon (step test) Wed Jan 28 11:49:20  2026 
# Stop Step: s07
#--------------------------------------------

#--------------------------------------------
#@# s03_mask_aseg: mri_mask Wed Jan 28 11:49:24  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/NMT2Sym
mri_mask mri/aseg.auto_noCCseg.mgz mri/mask.mgz mri/aseg.presurf.mgz

#--------------------------------------------
#@# s05_norm_t1: mri_mask Wed Jan 28 11:49:24  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/NMT2Sym
mri_mask mri/nu.mgz mri/mask.mgz mri/norm.mgz

#--------------------------------------------
#@# s07_wm_filled: mri_normalize Wed Jan 28 11:49:26  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/NMT2Sym
mri_normalize -seed 1234 -mprage -noconform -aseg mri/aseg.presurf.mgz -mask mri/brainmask.mgz mri/norm.mgz mri/brain.mgz

#--------------------------------------------
#@# s07_wm_filled: mri_mask Wed Jan 28 11:49:51  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/NMT2Sym
mri_mask -T 5 mri/brain.mgz mri/brainmask.mgz mri/brain.finalsurfs.mgz

#--------------------------------------------
#@# s07_wm_filled: mri_fill Wed Jan 28 11:49:51  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/NMT2Sym
mri_fill -a scripts/ponscc.cut.log -segmentation mri/aseg.presurf.mgz -ctab /usr/local/freesurfer/7.4.1/SubCorticalMassLUT.txt mri/wm.mgz mri/filled.mgz


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:56:47  2026 
# Run Step: s11
#--------------------------------------------


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:57:51  2026 
# Run Step: s14
#--------------------------------------------

#--------------------------------------------
#@# s14_parcellation: recon-all Thu Jan 29 14:57:51  2026
recon-all -s sub-NMT2Sym -hemi lh -cortex-label -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:58:03  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 5 -nw -seed 1234 surf/lh.white.preaparc surf/lh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:58:03  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 50 -nw -seed 1234 surf/lh.smoothwm surf/lh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Thu Jan 29 14:58:04  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_inflate -n 3 surf/lh.smoothwm.forinflate surf/lh.inflated.adjusted

#--------------------------------------------
#@# s14_parcellation: recon-all Thu Jan 29 14:58:05  2026
recon-all -s sub-NMT2Sym -hemi rh -cortex-label -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:58:17  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 5 -nw -seed 1234 surf/rh.white.preaparc surf/rh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:58:18  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 50 -nw -seed 1234 surf/rh.smoothwm surf/rh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Thu Jan 29 14:58:18  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_inflate -n 3 surf/rh.smoothwm.forinflate surf/rh.inflated.adjusted


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:58:58  2026 
# Run Step: s14
#--------------------------------------------

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:58:59  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 5 -nw -seed 1234 surf/lh.white.preaparc surf/lh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:58:59  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 50 -nw -seed 1234 surf/lh.smoothwm surf/lh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Thu Jan 29 14:59:00  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_inflate -n 2 surf/lh.smoothwm.forinflate surf/lh.inflated.adjusted


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:59:14  2026 
# Run Step: s14
#--------------------------------------------

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:59:15  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 5 -nw -seed 1234 surf/rh.white.preaparc surf/rh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:59:15  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 50 -nw -seed 1234 surf/rh.smoothwm surf/rh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Thu Jan 29 14:59:15  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_inflate -n 2 surf/rh.smoothwm.forinflate surf/rh.inflated.adjusted


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:59:29  2026 
# Run Step: s14
#--------------------------------------------

#--------------------------------------------
#@# s14_parcellation: recon-all Thu Jan 29 14:59:29  2026
recon-all -s sub-NMT2Sym -hemi lh -cortex-label -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:59:38  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 5 -nw -seed 1234 surf/lh.white.preaparc surf/lh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:59:38  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 50 -nw -seed 1234 surf/lh.smoothwm surf/lh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Thu Jan 29 14:59:39  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_inflate -n 2 surf/lh.smoothwm.forinflate surf/lh.inflated.adjusted

#--------------------------------------------
#@# s14_parcellation: recon-all Thu Jan 29 14:59:40  2026
recon-all -s sub-NMT2Sym -hemi rh -cortex-label -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:59:48  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 5 -nw -seed 1234 surf/rh.white.preaparc surf/rh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:59:49  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_smooth -n 50 -nw -seed 1234 surf/rh.smoothwm surf/rh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Thu Jan 29 14:59:49  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_inflate -n 2 surf/rh.smoothwm.forinflate surf/rh.inflated.adjusted


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:59:56  2026 
# Run Step: s16
#--------------------------------------------

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:56  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --curv-map surf/lh.white 2 10 surf/lh.curv

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:56  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --curv-map surf/lh.pial 2 10 surf/lh.curv.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:56  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --area-map surf/lh.white surf/lh.area

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:56  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --area-map surf/lh.pial surf/lh.area.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:56  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --thickness surf/lh.white surf/lh.pial 20 5 surf/lh.thickness

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:58  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --curv-map surf/rh.white 2 10 surf/rh.curv

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:59  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --curv-map surf/rh.pial 2 10 surf/rh.curv.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:59  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --area-map surf/rh.white surf/rh.area

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:59  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --area-map surf/rh.pial surf/rh.area.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:59:59  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mris_place_surface --thickness surf/rh.white surf/rh.pial 20 5 surf/rh.thickness


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 15:00:01  2026 
# Run Step: s17
#--------------------------------------------


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 15:00:01  2026 
# Run Step: s18
#--------------------------------------------

#--------------------------------------------
#@# s18_statistics: recon-all Thu Jan 29 15:00:01  2026
recon-all -s sub-NMT2Sym -hemi lh -curvstats -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s18_statistics: mris_anatomical_stats Thu Jan 29 15:00:06  2026
mris_anatomical_stats -th3 -mgz -b -cortex /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/label/lh.cortex.label -f /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/stats/lh.aparc.ARM2atlas.mapped.stats -a /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/label/lh.aparc.ARM2atlas.mapped.annot sub-NMT2Sym lh white

#--------------------------------------------
#@# s18_statistics: recon-all Thu Jan 29 15:00:07  2026
recon-all -s sub-NMT2Sym -hemi rh -curvstats -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s18_statistics: mris_anatomical_stats Thu Jan 29 15:00:11  2026
mris_anatomical_stats -th3 -mgz -b -cortex /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/label/rh.cortex.label -f /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/stats/rh.aparc.ARM2atlas.mapped.stats -a /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/label/rh.aparc.ARM2atlas.mapped.annot sub-NMT2Sym rh white


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 15:00:12  2026 
# Run Step: s19
#--------------------------------------------

#--------------------------------------------
#@# s19_cortical_ribbon: recon-all Thu Jan 29 15:00:12  2026
recon-all -s sub-NMT2Sym -cortribbon -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 15:00:35  2026 
# Run Step: s20
#--------------------------------------------

#--------------------------------------------
#@# s20_aseg_refinement: recon-all Thu Jan 29 15:00:35  2026
recon-all -s sub-NMT2Sym -hyporelabel -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s20_aseg_refinement: recon-all Thu Jan 29 15:00:46  2026
recon-all -s sub-NMT2Sym -apas2aseg -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 15:00:55  2026 
# Run Step: s21
#--------------------------------------------

#--------------------------------------------
#@# s21_aparc_mapping: mri_surf2volseg Thu Jan 29 15:00:55  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mri_surf2volseg --o mri/aparc.ARM2atlas+aseg.mapped.mgz --i mri/aseg.mgz --threads 8 --label-cortex --lh-annot label/lh.aparc.ARM2atlas.mapped.annot 1000 --lh-cortex-mask label/lh.cortex.label --lh-white surf/lh.white --lh-pial surf/lh.pial --rh-annot label/rh.aparc.ARM2atlas.mapped.annot 2000 --rh-cortex-mask label/rh.cortex.label --rh-white surf/rh.white --rh-pial surf/rh.pial


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 15:01:05  2026 
# Run Step: s22
#--------------------------------------------

#--------------------------------------------
#@# s22_wmparc_mapping: mri_surf2volseg Thu Jan 29 15:01:05  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym
mri_surf2volseg --o mri/wmparc.ARM2atlas.mapped.mgz --i mri/aparc.ARM2atlas+aseg.mapped.mgz --threads 8 --label-wm --lh-annot label/lh.aparc.ARM2atlas.mapped.annot 3000 --lh-cortex-mask label/lh.cortex.label --lh-white surf/lh.white --lh-pial surf/lh.pial --rh-annot label/rh.aparc.ARM2atlas.mapped.annot 4000 --rh-cortex-mask label/rh.cortex.label --rh-white surf/rh.white --rh-pial surf/rh.pial
