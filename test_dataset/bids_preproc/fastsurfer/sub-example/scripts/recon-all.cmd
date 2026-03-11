

#---------------------------------
# New invocation of recon-all Wed Mar 11 06:50:21 PM UTC 2026 
#--------------------------------------------
#@# AutoDetGWStats lh Wed Mar 11 06:50:21 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_autodet_gwstats --o ../surf/autodet.gw.stats.lh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/lh.orig.premesh


#---------------------------------
# New invocation of recon-all Wed Mar 11 06:50:32 PM UTC 2026 
#--------------------------------------------
#@# CortexLabel lh Wed Mar 11 06:50:32 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 0 ../label/lh.cortex.label
#--------------------------------------------
#@# CortexLabel+HipAmyg lh Wed Mar 11 06:50:33 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 1 ../label/lh.cortex+hipamyg.label


#---------------------------------
# New invocation of recon-all Wed Mar 11 06:50:34 PM UTC 2026 
#--------------------------------------------
#@# Curv .H and .K lh Wed Mar 11 06:50:34 PM UTC 2026

 mris_curvature -w -seed 1234 lh.white.preaparc 


 mris_curvature -seed 1234 -thresh .999 -n -a 5 -w -distances 10 10 lh.inflated 



#---------------------------------
# New invocation of recon-all Wed Mar 11 06:51:15 PM UTC 2026 
#--------------------------------------------
#@# AutoDetGWStats rh Wed Mar 11 06:51:15 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_autodet_gwstats --o ../surf/autodet.gw.stats.rh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/rh.orig.premesh


#---------------------------------
# New invocation of recon-all Wed Mar 11 06:51:25 PM UTC 2026 
#--------------------------------------------
#@# CortexLabel rh Wed Mar 11 06:51:26 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 0 ../label/rh.cortex.label
#--------------------------------------------
#@# CortexLabel+HipAmyg rh Wed Mar 11 06:51:26 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 1 ../label/rh.cortex+hipamyg.label


#---------------------------------
# New invocation of recon-all Wed Mar 11 06:51:27 PM UTC 2026 
#--------------------------------------------
#@# Curv .H and .K rh Wed Mar 11 06:51:27 PM UTC 2026

 mris_curvature -w -seed 1234 rh.white.preaparc 


 mris_curvature -seed 1234 -thresh .999 -n -a 5 -w -distances 10 10 rh.inflated 



#---------------------------------
# New invocation of recon-all Wed Mar 11 06:51:52 PM UTC 2026 
#@# white curv lh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
   Update not needed
#@# white area lh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
   Update not needed
#@# pial curv lh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
   Update not needed
#@# pial area lh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
   Update not needed
#@# thickness lh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# area and vertex vol lh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
#@# white curv rh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
   Update not needed
#@# white area rh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
   Update not needed
#@# pial curv rh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
   Update not needed
#@# pial area rh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
   Update not needed
#@# thickness rh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#@# area and vertex vol rh Wed Mar 11 06:51:53 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
#--------------------------------------------
#@# Cortical ribbon mask Wed Mar 11 06:51:53 PM UTC 2026

 mris_volmask --aseg_name aseg.presurf --label_left_white 2 --label_left_ribbon 3 --label_right_white 41 --label_right_ribbon 42 --save_ribbon sub-example 



#---------------------------------
# New invocation of recon-all Wed Mar 11 06:51:56 PM UTC 2026 
#@# white curv lh Wed Mar 11 06:51:56 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
   Update not needed
#@# white area lh Wed Mar 11 06:51:56 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
   Update not needed
#@# pial curv lh Wed Mar 11 06:51:56 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
   Update not needed
#@# pial area lh Wed Mar 11 06:51:56 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
   Update not needed
#@# thickness lh Wed Mar 11 06:51:56 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# area and vertex vol lh Wed Mar 11 06:51:56 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed

#-----------------------------------------
#@# Curvature Stats lh Wed Mar 11 06:51:56 PM UTC 2026

 mris_curvature_stats -m --writeCurvatureFiles -G -o ../stats/lh.curv.stats -F smoothwm sub-example lh curv sulc 



#---------------------------------
# New invocation of recon-all Wed Mar 11 06:51:57 PM UTC 2026 
#@# white curv rh Wed Mar 11 06:51:57 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
   Update not needed
#@# white area rh Wed Mar 11 06:51:57 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
   Update not needed
#@# pial curv rh Wed Mar 11 06:51:57 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
   Update not needed
#@# pial area rh Wed Mar 11 06:51:57 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
   Update not needed
#@# thickness rh Wed Mar 11 06:51:57 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#@# area and vertex vol rh Wed Mar 11 06:51:57 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed

#-----------------------------------------
#@# Curvature Stats rh Wed Mar 11 06:51:57 PM UTC 2026

 mris_curvature_stats -m --writeCurvatureFiles -G -o ../stats/rh.curv.stats -F smoothwm sub-example rh curv sulc 



#---------------------------------
# New invocation of recon-all Wed Mar 11 06:51:58 PM UTC 2026 
#@# white curv lh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
   Update not needed
#@# white area lh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
   Update not needed
#@# pial curv lh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
   Update not needed
#@# pial area lh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
   Update not needed
#@# thickness lh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# area and vertex vol lh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# white curv rh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
   Update not needed
#@# white area rh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
   Update not needed
#@# pial curv rh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
   Update not needed
#@# pial area rh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
   Update not needed
#@# thickness rh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#@# area and vertex vol rh Wed Mar 11 06:51:58 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#-----------------------------------------
#@# Relabel Hypointensities Wed Mar 11 06:51:58 PM UTC 2026

 mri_relabel_hypointensities aseg.presurf.mgz ../surf aseg.presurf.hypos.mgz 



#---------------------------------
# New invocation of recon-all Wed Mar 11 06:51:59 PM UTC 2026 
#@# white curv lh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv
   Update not needed
#@# white area lh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/lh.white ../surf/lh.area
   Update not needed
#@# pial curv lh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial
   Update not needed
#@# pial area lh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial
   Update not needed
#@# thickness lh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# area and vertex vol lh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness
   Update not needed
#@# white curv rh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv
   Update not needed
#@# white area rh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/rh.white ../surf/rh.area
   Update not needed
#@# pial curv rh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial
   Update not needed
#@# pial area rh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial
   Update not needed
#@# thickness rh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#@# area and vertex vol rh Wed Mar 11 06:51:59 PM UTC 2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri
mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness
   Update not needed
#-----------------------------------------
#@# APas-to-ASeg Wed Mar 11 06:51:59 PM UTC 2026

 mri_surf2volseg --o aseg.mgz --i aseg.presurf.hypos.mgz --fix-presurf-with-ribbon /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/mri/ribbon.mgz --threads 1 --lh-cortex-mask /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/label/lh.cortex.label --lh-white /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/surf/lh.white --lh-pial /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/surf/lh.pial --rh-cortex-mask /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/label/rh.cortex.label --rh-white /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/surf/rh.white --rh-pial /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/surf/rh.pial 

