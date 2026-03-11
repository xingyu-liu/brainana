

#---------------------------------
# New invocation of fastsurfer-recon Wed Mar 11 18:50:07  2026 
#--------------------------------------------

#--------------------------------------------
#@# s03_mask_aseg: mri_mask Wed Mar 11 18:50:08  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_mask mri/aseg.auto_noCCseg.mgz mri/mask.mgz mri/aseg.presurf.mgz

#--------------------------------------------
#@# s05_norm_t1: mri_mask Wed Mar 11 18:50:08  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_mask mri/nu.mgz mri/mask.mgz mri/norm.mgz

#--------------------------------------------
#@# s07_wm_filled: mri_normalize Wed Mar 11 18:50:08  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_normalize -seed 1234 -mprage -noconform -aseg mri/aseg.presurf.mgz -mask mri/brainmask.mgz mri/norm.mgz mri/brain.mgz

#--------------------------------------------
#@# s07_wm_filled: mri_mask Wed Mar 11 18:50:10  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_mask -T 5 mri/brain.mgz mri/brainmask.mgz mri/brain.finalsurfs.mgz

#--------------------------------------------
#@# s07_wm_filled: mri_fill Wed Mar 11 18:50:10  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_fill -a scripts/ponscc.cut.log -segmentation mri/aseg.presurf.mgz -ctab /usr/local/freesurfer/SubCorticalMassLUT.txt mri/wm.mgz mri/filled.mgz

#--------------------------------------------
#@# s08_tessellation: mri_pretess Wed Mar 11 18:50:10  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_pretess mri/filled.mgz 255 mri/brainmask.mgz mri/filled-pretess255.mgz

#--------------------------------------------
#@# s08_tessellation: mri_mc Wed Mar 11 18:50:10  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_mc mri/filled-pretess255.mgz 255 surf/lh.orig.nofix

#--------------------------------------------
#@# s08_tessellation: mris_info Wed Mar 11 18:50:10  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_info surf/lh.orig.nofix

#--------------------------------------------
#@# s08_tessellation: mris_extract_main_component Wed Mar 11 18:50:10  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_extract_main_component surf/lh.orig.nofix surf/lh.orig.nofix

#--------------------------------------------
#@# s08_tessellation: mris_info Wed Mar 11 18:50:11  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_info surf/lh.orig.nofix

#--------------------------------------------
#@# s09_smoothing: mris_smooth Wed Mar 11 18:50:11  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_smooth -n 20 -nw -seed 1234 surf/lh.orig.nofix surf/lh.smoothwm.nofix

#--------------------------------------------
#@# s10_inflation: mris_inflate Wed Mar 11 18:50:11  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_inflate -no-save-sulc -n 5 surf/lh.smoothwm.nofix surf/lh.inflated.nofix

#--------------------------------------------
#@# s12_topology_fix: mris_fix_topology Wed Mar 11 18:50:11  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/scripts
mris_fix_topology -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 sub-example lh

#--------------------------------------------
#@# s12_topology_fix: mris_remove_intersection Wed Mar 11 18:50:20  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_remove_intersection surf/lh.orig surf/lh.orig

#--------------------------------------------
#@# s12_topology_fix: mris_smooth Wed Mar 11 18:50:20  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_smooth -n 20 -nw -seed 1234 surf/lh.orig surf/lh.smoothwm

#--------------------------------------------
#@# s12_topology_fix: mris_inflate Wed Mar 11 18:50:20  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_inflate -n 5 surf/lh.smoothwm surf/lh.inflated

#--------------------------------------------
#@# s13_white_preaparc: recon-all Wed Mar 11 18:50:20  2026
recon-all -s sub-example -hemi lh -autodetgwstats -no-isrunning -umask 022

#--------------------------------------------
#@# s13_white_preaparc: mris_place_surface Wed Mar 11 18:50:21  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --adgws-in surf/autodet.gw.stats.lh.dat --seg mri/aseg.presurf.mgz --threads 1 --wm mri/wm.mgz --invol mri/brain.finalsurfs.mgz --lh --o surf/lh.white.preaparc --white --max-cbv-dist 5 --nsmooth 3 --i surf/lh.orig

#--------------------------------------------
#@# s14_parcellation: recon-all Wed Mar 11 18:50:32  2026
recon-all -s sub-example -hemi lh -cortex-label -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: recon-all Wed Mar 11 18:50:33  2026
recon-all -s sub-example -hemi lh -curvHK -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: mris_smooth Wed Mar 11 18:50:37  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_smooth -n 5 -nw -seed 1234 surf/lh.white.preaparc surf/lh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Wed Mar 11 18:50:37  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_smooth -n 50 -nw -seed 1234 surf/lh.smoothwm surf/lh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Wed Mar 11 18:50:37  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_inflate -n 3 surf/lh.smoothwm.forinflate surf/lh.inflated.adjusted

#--------------------------------------------
#@# s15_surface_placement: mris_place_surface Wed Mar 11 18:50:37  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --adgws-in surf/autodet.gw.stats.lh.dat --seg mri/aseg.presurf.mgz --threads 1 --wm mri/wm.mgz --invol mri/brain.finalsurfs.mgz --lh --o surf/lh.white --white --rip-label label/lh.cortex.label --rip-bg --rip-surf surf/lh.white.preaparc --aparc label/lh.aparc.ARM2atlas.mapped.annot --i surf/lh.white.preaparc

#--------------------------------------------
#@# s15_surface_placement: mris_place_surface Wed Mar 11 18:50:48  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --adgws-in surf/autodet.gw.stats.lh.dat --seg mri/aseg.presurf.mgz --threads 1 --wm mri/wm.mgz --invol mri/brain.finalsurfs.mgz --lh --o surf/lh.pial.T1 --pial --rip-label label/lh.cortex+hipamyg.label --pin-medial-wall label/lh.cortex.label --repulse-surf surf/lh.white --white-surf surf/lh.white --aparc label/lh.aparc.ARM2atlas.mapped.annot --i surf/lh.white

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:50:58  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --curv-map surf/lh.white 2 10 surf/lh.curv

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:50:58  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --curv-map surf/lh.pial 2 10 surf/lh.curv.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:50:59  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --area-map surf/lh.white surf/lh.area

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:50:59  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --area-map surf/lh.pial surf/lh.area.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:50:59  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --thickness surf/lh.white surf/lh.pial 20 5 surf/lh.thickness

#--------------------------------------------
#@# s08_tessellation: mri_pretess Wed Mar 11 18:51:00  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_pretess mri/filled.mgz 127 mri/brainmask.mgz mri/filled-pretess127.mgz

#--------------------------------------------
#@# s08_tessellation: mri_mc Wed Mar 11 18:51:00  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_mc mri/filled-pretess127.mgz 127 surf/rh.orig.nofix

#--------------------------------------------
#@# s08_tessellation: mris_info Wed Mar 11 18:51:00  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_info surf/rh.orig.nofix

#--------------------------------------------
#@# s08_tessellation: mris_extract_main_component Wed Mar 11 18:51:00  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_extract_main_component surf/rh.orig.nofix surf/rh.orig.nofix

#--------------------------------------------
#@# s08_tessellation: mris_info Wed Mar 11 18:51:00  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_info surf/rh.orig.nofix

#--------------------------------------------
#@# s09_smoothing: mris_smooth Wed Mar 11 18:51:00  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_smooth -n 20 -nw -seed 1234 surf/rh.orig.nofix surf/rh.smoothwm.nofix

#--------------------------------------------
#@# s10_inflation: mris_inflate Wed Mar 11 18:51:00  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_inflate -no-save-sulc -n 5 surf/rh.smoothwm.nofix surf/rh.inflated.nofix

#--------------------------------------------
#@# s12_topology_fix: mris_fix_topology Wed Mar 11 18:51:01  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/scripts
mris_fix_topology -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 sub-example rh

#--------------------------------------------
#@# s12_topology_fix: mris_remove_intersection Wed Mar 11 18:51:14  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_remove_intersection surf/rh.orig surf/rh.orig

#--------------------------------------------
#@# s12_topology_fix: mris_smooth Wed Mar 11 18:51:14  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_smooth -n 20 -nw -seed 1234 surf/rh.orig surf/rh.smoothwm

#--------------------------------------------
#@# s12_topology_fix: mris_inflate Wed Mar 11 18:51:14  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_inflate -n 5 surf/rh.smoothwm surf/rh.inflated

#--------------------------------------------
#@# s13_white_preaparc: recon-all Wed Mar 11 18:51:15  2026
recon-all -s sub-example -hemi rh -autodetgwstats -no-isrunning -umask 022

#--------------------------------------------
#@# s13_white_preaparc: mris_place_surface Wed Mar 11 18:51:16  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --adgws-in surf/autodet.gw.stats.rh.dat --seg mri/aseg.presurf.mgz --threads 1 --wm mri/wm.mgz --invol mri/brain.finalsurfs.mgz --rh --o surf/rh.white.preaparc --white --max-cbv-dist 5 --nsmooth 3 --i surf/rh.orig

#--------------------------------------------
#@# s14_parcellation: recon-all Wed Mar 11 18:51:25  2026
recon-all -s sub-example -hemi rh -cortex-label -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: recon-all Wed Mar 11 18:51:27  2026
recon-all -s sub-example -hemi rh -curvHK -no-isrunning -umask 022

#--------------------------------------------
#@# s14_parcellation: mris_smooth Wed Mar 11 18:51:30  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_smooth -n 5 -nw -seed 1234 surf/rh.white.preaparc surf/rh.smoothwm.adjusted

#--------------------------------------------
#@# s14_parcellation: mris_smooth Wed Mar 11 18:51:30  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_smooth -n 50 -nw -seed 1234 surf/rh.smoothwm surf/rh.smoothwm.forinflate

#--------------------------------------------
#@# s14_parcellation: mris_inflate Wed Mar 11 18:51:30  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_inflate -n 3 surf/rh.smoothwm.forinflate surf/rh.inflated.adjusted

#--------------------------------------------
#@# s15_surface_placement: mris_place_surface Wed Mar 11 18:51:30  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --adgws-in surf/autodet.gw.stats.rh.dat --seg mri/aseg.presurf.mgz --threads 1 --wm mri/wm.mgz --invol mri/brain.finalsurfs.mgz --rh --o surf/rh.white --white --rip-label label/rh.cortex.label --rip-bg --rip-surf surf/rh.white.preaparc --aparc label/rh.aparc.ARM2atlas.mapped.annot --i surf/rh.white.preaparc

#--------------------------------------------
#@# s15_surface_placement: mris_place_surface Wed Mar 11 18:51:39  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --adgws-in surf/autodet.gw.stats.rh.dat --seg mri/aseg.presurf.mgz --threads 1 --wm mri/wm.mgz --invol mri/brain.finalsurfs.mgz --rh --o surf/rh.pial.T1 --pial --rip-label label/rh.cortex+hipamyg.label --pin-medial-wall label/rh.cortex.label --repulse-surf surf/rh.white --white-surf surf/rh.white --aparc label/rh.aparc.ARM2atlas.mapped.annot --i surf/rh.white

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:51:51  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --curv-map surf/rh.white 2 10 surf/rh.curv

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:51:51  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --curv-map surf/rh.pial 2 10 surf/rh.curv.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:51:51  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --area-map surf/rh.white surf/rh.area

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:51:51  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --area-map surf/rh.pial surf/rh.area.pial

#--------------------------------------------
#@# s16_compute_morphometry: mris_place_surface Wed Mar 11 18:51:51  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mris_place_surface --thickness surf/rh.white surf/rh.pial 20 5 surf/rh.thickness

#--------------------------------------------
#@# s18_cortical_ribbon: recon-all Wed Mar 11 18:51:52  2026
recon-all -s sub-example -cortribbon -no-isrunning -umask 022

#--------------------------------------------
#@# s19_statistics: recon-all Wed Mar 11 18:51:56  2026
recon-all -s sub-example -hemi lh -curvstats -no-isrunning -umask 022

#--------------------------------------------
#@# s19_statistics: mris_anatomical_stats Wed Mar 11 18:51:56  2026
mris_anatomical_stats -th3 -mgz -b -cortex /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/label/lh.cortex.label -f /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/stats/lh.aparc.ARM2atlas.mapped.stats -a /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/label/lh.aparc.ARM2atlas.mapped.annot sub-example lh white

#--------------------------------------------
#@# s19_statistics: recon-all Wed Mar 11 18:51:57  2026
recon-all -s sub-example -hemi rh -curvstats -no-isrunning -umask 022

#--------------------------------------------
#@# s19_statistics: mris_anatomical_stats Wed Mar 11 18:51:57  2026
mris_anatomical_stats -th3 -mgz -b -cortex /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/label/rh.cortex.label -f /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/stats/rh.aparc.ARM2atlas.mapped.stats -a /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example/label/rh.aparc.ARM2atlas.mapped.annot sub-example rh white

#--------------------------------------------
#@# s20_aseg_refinement: recon-all Wed Mar 11 18:51:57  2026
recon-all -s sub-example -hyporelabel -no-isrunning -umask 022

#--------------------------------------------
#@# s20_aseg_refinement: recon-all Wed Mar 11 18:51:59  2026
recon-all -s sub-example -apas2aseg -no-isrunning -umask 022

#--------------------------------------------
#@# s21_aparc_mapping: mri_surf2volseg Wed Mar 11 18:52:00  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_surf2volseg --o mri/aparc.ARM2atlas+aseg.mapped.mgz --i mri/aseg.mgz --threads 1 --label-cortex --lh-annot label/lh.aparc.ARM2atlas.mapped.annot 1000 --lh-cortex-mask label/lh.cortex.label --lh-white surf/lh.white --lh-pial surf/lh.pial --rh-annot label/rh.aparc.ARM2atlas.mapped.annot 2000 --rh-cortex-mask label/rh.cortex.label --rh-white surf/rh.white --rh-pial surf/rh.pial

#--------------------------------------------
#@# s22_wmparc_mapping: mri_surf2volseg Wed Mar 11 18:52:01  2026
cd /output_wd/work/04/b857bf78293faa4c6556e1ed98af01/work/fastsurfer/sub-example
mri_surf2volseg --o mri/wmparc.ARM2atlas.mapped.mgz --i mri/aparc.ARM2atlas+aseg.mapped.mgz --threads 1 --label-wm --lh-annot label/lh.aparc.ARM2atlas.mapped.annot 3000 --lh-cortex-mask label/lh.cortex.label --lh-white surf/lh.white --lh-pial surf/lh.pial --rh-annot label/rh.aparc.ARM2atlas.mapped.annot 4000 --rh-cortex-mask label/rh.cortex.label --rh-white surf/rh.white --rh-pial surf/rh.pial
