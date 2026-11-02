"""Build a signed, navigation-only shortcut; signed output stays in ignored build/."""
import pathlib
import plistlib
import subprocess
import uuid

root = pathlib.Path(__file__).resolve().parents[1]
folder = root/'build/settings-shortcut'
folder.mkdir(parents=True,exist_ok=True)
identifier = str(uuid.uuid5(uuid.NAMESPACE_URL,'loc2:location-settings-url')).upper()
workflow = {
    'WFWorkflowClientVersion':'3036.0.4.2','WFWorkflowMinimumClientVersion':900,
    'WFWorkflowMinimumClientVersionString':'900','WFWorkflowName':'Loc2 定位服务',
    'WFWorkflowIcon':{'WFWorkflowIconStartColor':4282601983,'WFWorkflowIconGlyphNumber':59511},
    'WFWorkflowImportQuestions':[],'WFWorkflowTypes':[],'WFWorkflowInputContentItemClasses':[],
    'WFWorkflowActions':[
        {'WFWorkflowActionIdentifier':'is.workflow.actions.url',
         'WFWorkflowActionParameters':{'UUID':identifier,'WFURLActionURL':'prefs:root=Privacy&path=LOCATION'}},
        {'WFWorkflowActionIdentifier':'is.workflow.actions.openurl',
         'WFWorkflowActionParameters':{'WFInput':{'Value':{'Type':'ActionOutput','OutputUUID':identifier,'OutputName':'URL'},'WFSerializationType':'WFTextTokenAttachment'}}},
    ],
}
source = folder/'unsigned.shortcut'
target = folder/'Loc2 定位服务.shortcut'
payload = plistlib.dumps(workflow)
if not target.exists() or not source.exists() or source.read_bytes() != payload:
    source.write_bytes(payload)
    subprocess.run(['shortcuts','sign','--mode','anyone','--input',str(source),'--output',str(target)],check=True)
print(target)
