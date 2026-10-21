import arcpy
from arcpy.sa import *
arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("3D")
arcpy.CheckOutExtension("spatial")
arcpy.CheckOutExtension("ImageAnalyst")
arcpy.SetProgressor("step","Creating State Centroids...",0,50,1)
folder = r"c:\data\worldhistory"
sourcegdb = folder+r"\backup\world1492_20260311.gdb\"
scratchgdb = 
# ============================================================================================
# PROCESS STATES: select real states, centroid areas
arcpy.AddMessage("Processing State Polygons...")
States = sourcegdb+"states"
RealStates = "memory\\RealStates"
arcpy.analysis.Select(in_features=States, out_feature_class=RealStates, where_clause="color IS NOT NULL And color <> '0'")
arcpy.AddMessage("Generating state centroid areas...")
States_Ctr = "memory\\States_Ctr"
arcpy.management.FeatureToPoint(in_features=RealStates, out_feature_class=States_Ctr, point_location="INSIDE")
States_CtrBuff = "memory\\States_CtrBuff"
arcpy.analysis.PairwiseBuffer(in_features=States_Ctr, out_feature_class=States_CtrBuff, buffer_distance_or_field="5 Kilometers", method="GEODESIC")
States_CtrBuffSimp = "memory\\States_CtrBuffSimp"
with arcpy.EnvManager(transferGDBAttributeProperties=False):
    arcpy.cartography.SimplifyPolygon(in_features=States_CtrBuff, out_feature_class=States_CtrBuffSimp, algorithm="POINT_REMOVE", tolerance="500 Meters", collapsed_point_option="NO_KEEP", error_option="RESOLVE_ERRORS")
arcpy.SetProgressorPosition()
# ==========================================================
# PROCESS BOUNDARIES: Generate full buffer and half buffer
arcpy.SetProgressorLabel("Creating boundary buffers")
Boundary_Lines = sourcegdb+"Boundary_Lines"
boundaries = "memory\\boundaries"
arcpy.management.CopyFeatures(in_features=Boundary_Lines, out_feature_class=boundaries)
# Calculate buffer widths
boundaries_2 = arcpy.management.CalculateField(in_table=boundaries, field="buffdist", expression="math.pow(2.5,!certainty!)*125", field_type="DOUBLE")[0]
boundaries_3 = arcpy.management.CalculateField(in_table=boundaries_2, field="buffdisthalf", expression="math.pow(2.5,!certainty!)*62", field_type="DOUBLE")[0]
# Generate full buffers
boundarycolor = "memory\\boundarycolor"
arcpy.analysis.PairwiseIntersect(in_features=[boundaries_3, RealStates], out_feature_class=boundarycolor, output_type="LINE")
colorbuff = "memory\\colorbuff"
arcpy.analysis.PairwiseBuffer(in_features=boundarycolor, out_feature_class=colorbuff, buffer_distance_or_field="buffdist", dissolve_option="LIST", dissolve_field=["color","statetype"], method="GEODESIC")
ColorBuffSimp = "memory\\ColorBuffSimp"
with arcpy.EnvManager(transferGDBAttributeProperties=False):
    arcpy.cartography.SimplifyPolygon(in_features=colorbuff, out_feature_class=ColorBuffSimp, algorithm="POINT_REMOVE", tolerance="500 Meters", collapsed_point_option="NO_KEEP", error_option="RESOLVE_ERRORS")
# Generate half buffers
colorbuff2 = "memory\\colorbuff2"
arcpy.analysis.PairwiseBuffer(in_features=boundarycolor, out_feature_class=colorbuff2, buffer_distance_or_field="buffdisthalf", dissolve_option="LIST", dissolve_field=["color","statetype"], method="GEODESIC")
colorBuff2Simp= "memory\\colorbuff2simp"
with arcpy.EnvManager(transferGDBAttributeProperties=False):
    arcpy.cartography.SimplifyPolygon(in_features=colorbuff2, out_feature_class=colorBuff2Simp, algorithm="POINT_REMOVE", tolerance="500 Meters", collapsed_point_option="NO_KEEP", error_option="RESOLVE_ERRORS")
arcpy.SetProgressorPosition()
#============================================
# CREATE RASTER MEMBERSHIP FUNCTION FOR A COLOR (i) AND WHETHER WE ARE PROCESSING SOVEREIGN STATES OR SEMI-STATES
def generate(i,semi):
    suff="semi" if semi>0 else "sov"
    arcpy.SetProgressorLabel(f"Processing Color #{i} {suff}...")
    ss = "NOT" if semi ==0 else ""
    mem = 100.0 - 40.0*semi
    # dependent states and not-quite-states will have 50% membership
    s = f"color IN ('{i}', '{i}a') and statetype {ss} in ('constituent','colony','vassal','autonomous','collection')"
    selectstates = "memory\\selectStates"
    arcpy.analysis.Select(in_features=RealStates, out_feature_class=selectstates, where_clause=s)
    selectbuffer = "memory\\selectbuffer"
    arcpy.analysis.Select(in_features=ColorBuffSimp, out_feature_class=selectbuffer, where_clause=s)
    # outer edge is state polygon + buffer
    union = "memory\\union"
    arcpy.analysis.Union(in_features=[[selectstates, ""], [selectbuffer, ""]], out_feature_class=union, join_attributes="ONLY_FID")
    outer = "memory\\outer"
    arcpy.analysis.PairwiseDissolve(in_features=union, out_feature_class=outer, multi_part="SINGLE_PART")
    outer2 = arcpy.management.CalculateField(in_table=outer, field="membership", expression="0", field_type="SHORT")[0]
    # mid-range is state polygon
    selectstates2 = arcpy.management.CalculateField(in_table=selectstates, field="membership", expression=str(mem*0.35), field_type="SHORT")[0]
    # 75% is state polygon - half buffer
    bufferhalf = "memory\\bufferhalf"
    arcpy.analysis.Select(in_features=colorBuff2Simp, out_feature_class=bufferhalf, where_clause=s)
    erasehalf = "memory\\erasehalf"
    arcpy.analysis.PairwiseErase(in_features=selectstates, erase_features=bufferhalf, out_feature_class=erasehalf)
    erasehalf2 = arcpy.management.CalculateField(in_table=erasehalf, field="membership", expression=str(mem*0.75), field_type="SHORT")[0]
    # interior is state polygon - buffer
    erase = "memory\\erase"
    arcpy.analysis.PairwiseErase(in_features=selectstates, erase_features=selectbuffer, out_feature_class=erase)
    erase2 = arcpy.management.CalculateField(in_table=erase, field="membership", expression=str(mem), field_type="SHORT")[0]
    # minimal interior is centroid buffer
    States_Ctr1 = "memory\\selectCtr"
    arcpy.analysis.Select(in_features=States_CtrBuffSimp, out_feature_class=States_Ctr1, where_clause=s)
    ctr2 = arcpy.management.CalculateField(in_table=States_Ctr1, field="membership", expression=str(mem), field_type="SHORT")[0]
    arcpy.SetProgressorPosition() # i*16+semi*8+2-16)    
    # generate TIN from points
    arcpy.SetProgressorLabel(f"Generating TIN {i} {suff}...")
    arcpy.AddMessage(f"Generating TIN {i} {suff} from {outer}, {selectstates}, {States_Ctr1}, {erase}, {erasehalf}")
    tin = folder+f"\\tin{i}_{suff}"
    arcpy.ddd.CreateTin(out_tin=tin, in_features= [[outer2, "membership", "Hard_Clip", "<None>"], [selectstates2, "membership", "Hard_Line", "<None>"], [ctr2, "membership", "Hard_Replace", "<None>"], [erase2, "membership", "Hard_Replace", "<None>"], [erasehalf2, "membership", "Hard_Line", "<None>"]], constrained_delaunay="CONSTRAINED_DELAUNAY")
    arcpy.SetProgressorPosition() # i*16+semi*8+4-16)
    tinraster = folder+f"\\tinraster{i}_{suff}"
    arcpy.ddd.TinRaster(in_tin=tin, out_raster=tinraster, sample_distance = "CELLSIZE 0.02")
    arcpy.SetProgressorPosition() # i*16+semi*8+6-16)    
    # Apply curve
    tinraster1 = arcpy.Raster(tinraster)
    arcpy.SetProgressorLabel(f"Generating raster {i} {suff}...")
    tinras2 = tinraster1/100.0
    power1 = Power(tinras2,2.7)
    Color1 =  power1 / (power1 + Power(1-tinras2,1.2))
#    colorRaster = f"c:/data/worldhistory/color{i}_{suff}.tif"
    
#============================================
# CREATE RASTER MEMBERSHIP FUNCTION FOR EACH COLOR
for i in range(1,8):
    generate(i,0)
    generate(i,1)


    
