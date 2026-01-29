

#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 13:43:09  2026 
# Run Step: s01
#--------------------------------------------


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 13:43:09  2026 
# Run Step: s02
#--------------------------------------------


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 13:43:13  2026 
# Run Step: s03
#--------------------------------------------

#--------------------------------------------
#@# s03_mask_aseg: mri_mask Thu Jan 29 13:43:13  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/MEBRAIN_resue
mri_mask mri/aseg.auto_noCCseg.mgz mri/mask.mgz mri/aseg.presurf.mgz


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 13:43:13  2026 
# Run Step: s04
#--------------------------------------------


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 13:43:13  2026 
# Run Step: s05
#--------------------------------------------

#--------------------------------------------
#@# s05_norm_t1: mri_mask Thu Jan 29 13:43:13  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/MEBRAIN_resue
mri_mask mri/nu.mgz mri/mask.mgz mri/norm.mgz


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 13:43:13  2026 
# Run Step: s06
#--------------------------------------------


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 13:43:13  2026 
# Run Step: s07
#--------------------------------------------

#--------------------------------------------
#@# s07_wm_filled: mri_normalize Thu Jan 29 13:43:15  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/MEBRAIN_resue
mri_normalize -seed 1234 -mprage -noconform -aseg mri/aseg.presurf.mgz -mask mri/brainmask.mgz mri/norm.mgz mri/brain.mgz

#--------------------------------------------
#@# s07_wm_filled: mri_mask Thu Jan 29 13:44:21  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/MEBRAIN_resue
mri_mask -T 5 mri/brain.mgz mri/brainmask.mgz mri/brain.finalsurfs.mgz

#--------------------------------------------
#@# s07_wm_filled: mri_fill Thu Jan 29 13:44:22  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/MEBRAIN_resue
mri_fill -a scripts/ponscc.cut.log -segmentation mri/aseg.presurf.mgz -ctab /usr/local/freesurfer/7.4.1/SubCorticalMassLUT.txt mri/wm.mgz mri/filled.mgz


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:50:09  2026 
# Run Step: s11
#--------------------------------------------


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:50:37  2026 
# Run Step: s14
#--------------------------------------------

#--------------------------------------------
#@# s14_parcellation: recon-all Thu Jan 29 14:50:37  2026
recon-all -s sub-MEBRAIN -hemi lh -cortex-label -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:51:05  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_smooth -n 5 -nw -seed 1234 surf/lh.white.preaparc surf/lh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:51:06  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_smooth -n 50 -nw -seed 1234 surf/lh.smoothwm surf/lh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Thu Jan 29 14:51:07  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_inflate -n 3 surf/lh.smoothwm.forinflate surf/lh.inflated.adjusted

#--------------------------------------------
#@# s14_parcellation: recon-all Thu Jan 29 14:51:11  2026
recon-all -s sub-MEBRAIN -hemi rh -cortex-label -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:51:39  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_smooth -n 5 -nw -seed 1234 surf/rh.white.preaparc surf/rh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Thu Jan 29 14:51:40  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_smooth -n 50 -nw -seed 1234 surf/rh.smoothwm surf/rh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Thu Jan 29 14:51:41  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_inflate -n 3 surf/rh.smoothwm.forinflate surf/rh.inflated.adjusted


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:51:50  2026 
# Run Step: s16
#--------------------------------------------

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:51:50  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --curv-map surf/lh.white 2 10 surf/lh.curv

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:51:51  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --curv-map surf/lh.pial 2 10 surf/lh.curv.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:51:52  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --area-map surf/lh.white surf/lh.area

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:51:52  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --area-map surf/lh.pial surf/lh.area.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:51:52  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --thickness surf/lh.white surf/lh.pial 20 5 surf/lh.thickness

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:52:01  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --curv-map surf/rh.white 2 10 surf/rh.curv

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:52:02  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --curv-map surf/rh.pial 2 10 surf/rh.curv.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:52:03  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --area-map surf/rh.white surf/rh.area

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:52:03  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --area-map surf/rh.pial surf/rh.area.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Thu Jan 29 14:52:03  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mris_place_surface --thickness surf/rh.white surf/rh.pial 20 5 surf/rh.thickness


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:52:13  2026 
# Run Step: s17
#--------------------------------------------


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:52:13  2026 
# Run Step: s18
#--------------------------------------------

#--------------------------------------------
#@# s18_statistics: recon-all Thu Jan 29 14:52:13  2026
recon-all -s sub-MEBRAIN -hemi lh -curvstats -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s18_statistics: mris_anatomical_stats Thu Jan 29 14:52:18  2026
mris_anatomical_stats -th3 -mgz -b -cortex /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN/label/lh.cortex.label -f /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN/stats/lh.aparc.ARM2atlas.mapped.stats -a /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN/label/lh.aparc.ARM2atlas.mapped.annot sub-MEBRAIN lh white

#--------------------------------------------
#@# s18_statistics: recon-all Thu Jan 29 14:52:23  2026
recon-all -s sub-MEBRAIN -hemi rh -curvstats -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s18_statistics: mris_anatomical_stats Thu Jan 29 14:52:28  2026
mris_anatomical_stats -th3 -mgz -b -cortex /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN/label/rh.cortex.label -f /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN/stats/rh.aparc.ARM2atlas.mapped.stats -a /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN/label/rh.aparc.ARM2atlas.mapped.annot sub-MEBRAIN rh white


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:52:31  2026 
# Run Step: s19
#--------------------------------------------

#--------------------------------------------
#@# s19_cortical_ribbon: recon-all Thu Jan 29 14:52:31  2026
recon-all -s sub-MEBRAIN -cortribbon -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:54:16  2026 
# Run Step: s20
#--------------------------------------------

#--------------------------------------------
#@# s20_aseg_refinement: recon-all Thu Jan 29 14:54:16  2026
recon-all -s sub-MEBRAIN -hyporelabel -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022

#--------------------------------------------
#@# s20_aseg_refinement: recon-all Thu Jan 29 14:54:41  2026
recon-all -s sub-MEBRAIN -apas2aseg -hires -threads 8 -itkthreads 8 -no-isrunning -umask 022


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:55:01  2026 
# Run Step: s21
#--------------------------------------------

#--------------------------------------------
#@# s21_aparc_mapping: mri_surf2volseg Thu Jan 29 14:55:01  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mri_surf2volseg --o mri/aparc.ARM2atlas+aseg.mapped.mgz --i mri/aseg.mgz --threads 8 --label-cortex --lh-annot label/lh.aparc.ARM2atlas.mapped.annot 1000 --lh-cortex-mask label/lh.cortex.label --lh-white surf/lh.white --lh-pial surf/lh.pial --rh-annot label/rh.aparc.ARM2atlas.mapped.annot 2000 --rh-cortex-mask label/rh.cortex.label --rh-white surf/rh.white --rh-pial surf/rh.pial


#---------------------------------
# New invocation of fastsurfer-recon (single stage) Thu Jan 29 14:55:45  2026 
# Run Step: s22
#--------------------------------------------

#--------------------------------------------
#@# s22_wmparc_mapping: mri_surf2volseg Thu Jan 29 14:55:45  2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-MEBRAIN
mri_surf2volseg --o mri/wmparc.ARM2atlas.mapped.mgz --i mri/aparc.ARM2atlas+aseg.mapped.mgz --threads 8 --label-wm --lh-annot label/lh.aparc.ARM2atlas.mapped.annot 3000 --lh-cortex-mask label/lh.cortex.label --lh-white surf/lh.white --lh-pial surf/lh.pial --rh-annot label/rh.aparc.ARM2atlas.mapped.annot 4000 --rh-cortex-mask label/rh.cortex.label --rh-white surf/rh.white --rh-pial surf/rh.pial
