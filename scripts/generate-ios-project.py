#!/usr/bin/env python3
"""Generate a small, deterministic Xcode project without third-party tooling."""
from pathlib import Path
import hashlib, plistlib
root=Path(__file__).resolve().parents[1]
base=root/'native/loc2-ios'
project=base/'loc2.xcodeproj';project.mkdir(exist_ok=True)
objects={}
def uid(name):return hashlib.sha1(name.encode()).hexdigest()[:24].upper()
def obj(name,value):objects[uid(name)]=value;return uid(name)
sources=[];files=[]
for path in sorted(base.glob('*.swift')):
 ref=obj('ref-'+path.name,{'isa':'PBXFileReference','lastKnownFileType':'sourcecode.swift','path':path.name,'sourceTree':'<group>'});files.append(ref)
 sources.append(obj('build-'+path.name,{'isa':'PBXBuildFile','fileRef':ref}))
asset=obj('assets',{'isa':'PBXFileReference','lastKnownFileType':'folder.assetcatalog','path':'Assets.xcassets','sourceTree':'<group>'});files.append(asset)
asset_build=obj('asset-build',{'isa':'PBXBuildFile','fileRef':asset})
notice=obj('notice',{'isa':'PBXFileReference','lastKnownFileType':'text','path':'ThirdPartyNotices.txt','sourceTree':'<group>'});files.append(notice)
notice_build=obj('notice-build',{'isa':'PBXBuildFile','fileRef':notice})
shortcut=obj('location-shortcut',{'isa':'PBXFileReference','lastKnownFileType':'file','path':'../../build/settings-shortcut/Loc2 定位服务.shortcut','sourceTree':'<group>'});files.append(shortcut)
shortcut_build=obj('location-shortcut-build',{'isa':'PBXBuildFile','fileRef':shortcut})
product=obj('product',{'isa':'PBXFileReference','explicitFileType':'wrapper.application','path':'Loc2.app','sourceTree':'BUILT_PRODUCTS_DIR'})
products=obj('products',{'isa':'PBXGroup','children':[product],'name':'Products','sourceTree':'<group>'})
group=obj('main-group',{'isa':'PBXGroup','children':files+[products],'sourceTree':'<group>'})
phase=obj('sources',{'isa':'PBXSourcesBuildPhase','buildActionMask':'2147483647','files':sources,'runOnlyForDeploymentPostprocessing':'0'})
framework=obj('framework',{'isa':'PBXFrameworksBuildPhase','buildActionMask':'2147483647','files':[],'runOnlyForDeploymentPostprocessing':'0'})
resources=obj('resources',{'isa':'PBXResourcesBuildPhase','buildActionMask':'2147483647','files':[asset_build,notice_build,shortcut_build],'runOnlyForDeploymentPostprocessing':'0'})
projectConfigs=[];targetConfigs=[]
for name in ['Debug','Release']:
 projectConfigs.append(obj('project-'+name,{'isa':'XCBuildConfiguration','name':name,'buildSettings':{'SDKROOT':'iphoneos','IPHONEOS_DEPLOYMENT_TARGET':'17.0','CLANG_ENABLE_MODULES':'YES','SWIFT_VERSION':'5.0'}}))
 settings={'ASSETCATALOG_COMPILER_APPICON_NAME':'AppIcon','PRODUCT_BUNDLE_IDENTIFIER':'local.loc2.mobile','PRODUCT_NAME':'Loc2','INFOPLIST_FILE':'Info.plist','CODE_SIGN_STYLE':'Automatic','TARGETED_DEVICE_FAMILY':'1','SWIFT_VERSION':'5.0','CURRENT_PROJECT_VERSION':'1','MARKETING_VERSION':'0.1.0','ENABLE_PREVIEWS':'YES','GENERATE_INFOPLIST_FILE':'NO','SUPPORTED_PLATFORMS':'iphoneos iphonesimulator','SWIFT_OPTIMIZATION_LEVEL':'-Onone' if name=='Debug' else '-O','LD_RUNPATH_SEARCH_PATHS':'$(inherited) @executable_path/Frameworks'}
 targetConfigs.append(obj('target-'+name,{'isa':'XCBuildConfiguration','name':name,'buildSettings':settings}))
pconfigs=obj('pconfigs',{'isa':'XCConfigurationList','buildConfigurations':projectConfigs,'defaultConfigurationIsVisible':'0','defaultConfigurationName':'Release'})
tconfigs=obj('tconfigs',{'isa':'XCConfigurationList','buildConfigurations':targetConfigs,'defaultConfigurationIsVisible':'0','defaultConfigurationName':'Release'})
target=obj('target',{'isa':'PBXNativeTarget','buildConfigurationList':tconfigs,'buildPhases':[phase,framework,resources],'buildRules':[],'dependencies':[],'name':'loc2','productName':'Loc2','productReference':product,'productType':'com.apple.product-type.application'})
pid=obj('project',{'isa':'PBXProject','attributes':{'LastUpgradeCheck':'2660','TargetAttributes':{target:{'CreatedOnToolsVersion':'26.6'}}},'buildConfigurationList':pconfigs,'compatibilityVersion':'Xcode 14.0','developmentRegion':'zh-Hans','hasScannedForEncodings':'0','knownRegions':['zh-Hans','en','Base'],'mainGroup':group,'productRefGroup':products,'projectDirPath':'','projectRoot':'','targets':[target]})
def quote(value):
 if isinstance(value,dict):return '{ '+ ' '.join(quote(str(k))+' = '+quote(v)+';' for k,v in value.items())+' }'
 if isinstance(value,list):return '( '+', '.join(quote(v) for v in value)+', )' if value else '()'
 return '"'+str(value).replace('\\','\\\\').replace('"','\\"')+'"'
(project/'project.pbxproj').write_text('// !$*UTF8*$!\n'+quote({'archiveVersion':'1','classes':{},'objectVersion':'56','objects':objects,'rootObject':pid})+'\n')
info={'CFBundleDevelopmentRegion':'zh-Hans','CFBundleDisplayName':'Loc2','CFBundleExecutable':'$(EXECUTABLE_NAME)','CFBundleIdentifier':'$(PRODUCT_BUNDLE_IDENTIFIER)','CFBundleName':'$(PRODUCT_NAME)','CFBundlePackageType':'APPL','CFBundleShortVersionString':'$(MARKETING_VERSION)','CFBundleVersion':'$(CURRENT_PROJECT_VERSION)','LSRequiresIPhoneOS':True,'UILaunchScreen':{},'UISupportedInterfaceOrientations':['UIInterfaceOrientationPortrait'],'NSCameraUsageDescription':'扫描 Mac 显示的二维码，建立你确认的控制连接。','NSLocalNetworkUsageDescription':'连接同一网络中的 Mac 后台服务，应用或停止你选定的目标位置。','NSLocationWhenInUseUsageDescription':'在 App 地图上显示系统报告位置，观察目标位置采用及停止后的恢复情况。','NSBonjourServices':['_loc2._tcp.'],'NSAppTransportSecurity':{'NSAllowsLocalNetworking':True},'CFBundleURLTypes':[{'CFBundleURLName':'local.loc2.pair','CFBundleURLSchemes':['loc2']}]}
(base/'Info.plist').write_bytes(plistlib.dumps(info))
print(project)
