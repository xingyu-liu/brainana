

#---------------------------------
# New invocation of recon-all Thu Jan 29 14:57:35 EST 2026 
#--------------------------------------------
#@# AutoDetGWStats lh Thu Jan 29 14:57:35 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_autodet_gwstats --o ../surf/autodet.gw.stats.lh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/lh.orig.premesh


#---------------------------------
# New invocation of recon-all Thu Jan 29 14:57:42 EST 2026 
#--------------------------------------------
#@# AutoDetGWStats rh Thu Jan 29 14:57:42 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_autodet_gwstats --o ../surf/autodet.gw.stats.rh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/rh.orig.premesh


#---------------------------------
# New invocation of recon-all Thu Jan 29 14:57:51 EST 2026 
#--------------------------------------------
#@# CortexLabel lh Thu Jan 29 14:57:52 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 0 ../label/lh.cortex.label
#--------------------------------------------
#@# CortexLabel+HipAmyg lh Thu Jan 29 14:57:54 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 1 ../label/lh.cortex+hipamyg.label
#@# white curv lh Thu Jan 29 14:57:56 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
#@# white area lh Thu Jan 29 14:57:57 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
#@# pial curv lh Thu Jan 29 14:57:58 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
#@# pial area lh Thu Jan 29 14:57:58 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
#@# thickness lh Thu Jan 29 14:57:59 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
#@# area and vertex vol lh Thu Jan 29 14:58:01 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness


#---------------------------------
# New invocation of recon-all Thu Jan 29 14:58:05 EST 2026 
#--------------------------------------------
#@# CortexLabel rh Thu Jan 29 14:58:06 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 0 ../label/rh.cortex.label
#--------------------------------------------
#@# CortexLabel+HipAmyg rh Thu Jan 29 14:58:08 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 1 ../label/rh.cortex+hipamyg.label
#@# white curv rh Thu Jan 29 14:58:10 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
#@# white area rh Thu Jan 29 14:58:11 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
#@# pial curv rh Thu Jan 29 14:58:12 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
#@# pial area rh Thu Jan 29 14:58:12 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
#@# thickness rh Thu Jan 29 14:58:13 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
#@# area and vertex vol rh Thu Jan 29 14:58:16 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness


#---------------------------------
# New invocation of recon-all Thu Jan 29 14:59:30 EST 2026 
#--------------------------------------------
#@# CortexLabel lh Thu Jan 29 14:59:30 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 0 ../label/lh.cortex.label
#--------------------------------------------
#@# CortexLabel+HipAmyg lh Thu Jan 29 14:59:32 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 1 ../label/lh.cortex+hipamyg.label
#@# white curv lh Thu Jan 29 14:59:35 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
   Update not needed
#@# white area lh Thu Jan 29 14:59:35 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
   Update not needed
#@# pial curv lh Thu Jan 29 14:59:35 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
   Update not needed
#@# pial area lh Thu Jan 29 14:59:36 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
   Update not needed
#@# thickness lh Thu Jan 29 14:59:36 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# area and vertex vol lh Thu Jan 29 14:59:37 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed


#---------------------------------
# New invocation of recon-all Thu Jan 29 14:59:40 EST 2026 
#--------------------------------------------
#@# CortexLabel rh Thu Jan 29 14:59:40 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 0 ../label/rh.cortex.label
#--------------------------------------------
#@# CortexLabel+HipAmyg rh Thu Jan 29 14:59:43 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 1 ../label/rh.cortex+hipamyg.label
#@# white curv rh Thu Jan 29 14:59:45 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
   Update not needed
#@# white area rh Thu Jan 29 14:59:45 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
   Update not needed
#@# pial curv rh Thu Jan 29 14:59:46 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
   Update not needed
#@# pial area rh Thu Jan 29 14:59:46 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
   Update not needed
#@# thickness rh Thu Jan 29 14:59:47 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#@# area and vertex vol rh Thu Jan 29 14:59:47 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed


#---------------------------------
# New invocation of recon-all Thu Jan 29 15:00:02 EST 2026 
#@# white curv lh Thu Jan 29 15:00:02 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
   Update not needed
#@# white area lh Thu Jan 29 15:00:02 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
   Update not needed
#@# pial curv lh Thu Jan 29 15:00:03 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
   Update not needed
#@# pial area lh Thu Jan 29 15:00:03 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
   Update not needed
#@# thickness lh Thu Jan 29 15:00:04 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# area and vertex vol lh Thu Jan 29 15:00:04 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness

#-----------------------------------------
#@# Curvature Stats lh Thu Jan 29 15:00:05 EST 2026

 mris_curvature_stats -m --writeCurvatureFiles -G -o ../stats/lh.curv.stats -F smoothwm sub-NMT2Sym lh curv sulc 



#---------------------------------
# New invocation of recon-all Thu Jan 29 15:00:07 EST 2026 
#@# white curv rh Thu Jan 29 15:00:07 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
   Update not needed
#@# white area rh Thu Jan 29 15:00:08 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
   Update not needed
#@# pial curv rh Thu Jan 29 15:00:08 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
   Update not needed
#@# pial area rh Thu Jan 29 15:00:09 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
   Update not needed
#@# thickness rh Thu Jan 29 15:00:09 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#@# area and vertex vol rh Thu Jan 29 15:00:10 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness

#-----------------------------------------
#@# Curvature Stats rh Thu Jan 29 15:00:11 EST 2026

 mris_curvature_stats -m --writeCurvatureFiles -G -o ../stats/rh.curv.stats -F smoothwm sub-NMT2Sym rh curv sulc 



#---------------------------------
# New invocation of recon-all Thu Jan 29 15:00:12 EST 2026 
#@# white curv lh Thu Jan 29 15:00:13 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
   Update not needed
#@# white area lh Thu Jan 29 15:00:13 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
   Update not needed
#@# pial curv lh Thu Jan 29 15:00:13 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
   Update not needed
#@# pial area lh Thu Jan 29 15:00:14 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
   Update not needed
#@# thickness lh Thu Jan 29 15:00:14 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# area and vertex vol lh Thu Jan 29 15:00:15 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# white curv rh Thu Jan 29 15:00:16 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
   Update not needed
#@# white area rh Thu Jan 29 15:00:16 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
   Update not needed
#@# pial curv rh Thu Jan 29 15:00:16 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
   Update not needed
#@# pial area rh Thu Jan 29 15:00:17 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
   Update not needed
#@# thickness rh Thu Jan 29 15:00:17 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#@# area and vertex vol rh Thu Jan 29 15:00:18 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#--------------------------------------------
#@# Cortical ribbon mask Thu Jan 29 15:00:19 EST 2026

 mris_volmask --aseg_name aseg.presurf --label_left_white 2 --label_left_ribbon 3 --label_right_white 41 --label_right_ribbon 42 --save_ribbon sub-NMT2Sym 



#---------------------------------
# New invocation of recon-all Thu Jan 29 15:00:35 EST 2026 
#@# white curv lh Thu Jan 29 15:00:35 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
   Update not needed
#@# white area lh Thu Jan 29 15:00:36 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
   Update not needed
#@# pial curv lh Thu Jan 29 15:00:36 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
   Update not needed
#@# pial area lh Thu Jan 29 15:00:37 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
   Update not needed
#@# thickness lh Thu Jan 29 15:00:37 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# area and vertex vol lh Thu Jan 29 15:00:37 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# white curv rh Thu Jan 29 15:00:38 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
   Update not needed
#@# white area rh Thu Jan 29 15:00:39 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
   Update not needed
#@# pial curv rh Thu Jan 29 15:00:39 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
   Update not needed
#@# pial area rh Thu Jan 29 15:00:40 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
   Update not needed
#@# thickness rh Thu Jan 29 15:00:40 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#@# area and vertex vol rh Thu Jan 29 15:00:40 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#-----------------------------------------
#@# Relabel Hypointensities Thu Jan 29 15:00:41 EST 2026

 mri_relabel_hypointensities aseg.presurf.mgz ../surf aseg.presurf.hypos.mgz 



#---------------------------------
# New invocation of recon-all Thu Jan 29 15:00:46 EST 2026 
#@# white curv lh Thu Jan 29 15:00:46 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
   Update not needed
#@# white area lh Thu Jan 29 15:00:47 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
   Update not needed
#@# pial curv lh Thu Jan 29 15:00:47 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
   Update not needed
#@# pial area lh Thu Jan 29 15:00:48 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
   Update not needed
#@# thickness lh Thu Jan 29 15:00:48 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# area and vertex vol lh Thu Jan 29 15:00:48 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# white curv rh Thu Jan 29 15:00:49 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
   Update not needed
#@# white area rh Thu Jan 29 15:00:50 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
   Update not needed
#@# pial curv rh Thu Jan 29 15:00:50 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
   Update not needed
#@# pial area rh Thu Jan 29 15:00:51 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
   Update not needed
#@# thickness rh Thu Jan 29 15:00:51 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#@# area and vertex vol rh Thu Jan 29 15:00:51 EST 2026
cd /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#-----------------------------------------
#@# APas-to-ASeg Thu Jan 29 15:00:52 EST 2026

 mri_surf2volseg --o aseg.mgz --i aseg.presurf.hypos.mgz --fix-presurf-with-ribbon /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/mri/ribbon.mgz --threads 8 --lh-cortex-mask /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/label/lh.cortex.label --lh-white /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/surf/lh.white --lh-pial /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/surf/lh.pial --rh-cortex-mask /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/label/rh.cortex.label --rh-white /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/surf/rh.white --rh-pial /mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym/surf/rh.pial 

