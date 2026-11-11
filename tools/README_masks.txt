mask_lattice.jpg: post-processed from blender/textures/mask_lattice_orig.jpg (horizontal blur of rows 1300+ so the eave-rafter
notches near the camera read as one soft shade band):
  ffmpeg -i blender/textures/mask_lattice_orig.jpg -filter_complex "[0]split[a][b];[b]crop=1600:780:0:1300,gblur=sigma=45:sigmaV=3[bl];[a][bl]overlay=0:1300" -q:v 2 app/assets/scene/mask_lattice.jpg
then (04/11) the near edge of the sun patch gets a penumbra: a vertical blur blended in from y 1180 to 1320 (no seam):
  ffmpeg -i blender/textures/mask_lattice_orig.jpg -filter_complex "[0]split[a][b];[b]crop=1600:780:0:1300,gblur=sigma=45:sigmaV=3[bl];[a][bl]overlay=0:1300,format=gray" -f rawvideo - \
    | $BLENDER_PY -I tools/feather_mask.py | ffmpeg -f rawvideo -pix_fmt gray -s 1600x2080 -i - -q:v 2 app/assets/scene/mask_lattice.jpg
