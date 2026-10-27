"""Generates GTM-croaccelerate-container.json (import: GTM → Admin → Import Container → Merge).
Replace the 4 constants after import: GA4 ID, Ads conversion ID + 2 labels, LinkedIn partner id."""
import json, datetime
T=lambda k,v:{"type":"TEMPLATE","key":k,"value":v}
B=lambda k,v:{"type":"BOOLEAN","key":k,"value":"true" if v else "false"}
I=lambda k,v:{"type":"INTEGER","key":k,"value":str(v)}
ids={"n":0}
def nid():
    ids["n"]+=1; return str(ids["n"])
ALL_PAGES="2147479553"; INIT="2147479573"
variables=[]; triggers=[]; tags=[]
def const(name,val):
    variables.append({"accountId":"0","containerId":"0","variableId":nid(),"name":name,"type":"c","parameter":[T("value",val)]})
def dlv(name,key):
    variables.append({"accountId":"0","containerId":"0","variableId":nid(),"name":name,"type":"v","parameter":[I("dataLayerVersion",2),B("setDefaultValue",False),T("name",key)]})
const("CONST - GA4 Measurement ID","G-XXXXXXXXXX")
const("CONST - Google Ads Conversion ID","AW-XXXXXXXXXX")
const("CONST - Ads Label - Lead","XXXXXXXXXXXXXXXX")
const("CONST - Ads Label - Call Booked","YYYYYYYYYYYYYYYY")
const("CONST - LinkedIn Partner ID","0000000")
const("CONST - LinkedIn Conversion ID - Lead","00000000")
for k in ["form_name","lead_type","company_size","interest","score","score_level","cta_id","cta_text","percent","page_type","content_group","lead_source_form"]:
    dlv("DLV - "+k,k)
def ce(event):
    tid=nid()
    triggers.append({"accountId":"0","containerId":"0","triggerId":tid,"name":"CE - "+event,"type":"CUSTOM_EVENT",
      "customEventFilter":[{"type":"EQUALS","parameter":[T("arg0","{{_event}}"),T("arg1",event)]}]})
    return tid
def params(*keys):
    return {"type":"LIST","key":"eventSettingsTable","list":[{"type":"MAP","map":[T("parameter",k),T("parameterValue","{{DLV - %s}}"%k)]} for k in keys]}
# Google tag
tags.append({"accountId":"0","containerId":"0","tagId":nid(),"name":"Google tag - GA4","type":"googtag",
  "parameter":[T("tagId","{{CONST - GA4 Measurement ID}}"),
    {"type":"LIST","key":"configSettingsTable","list":[{"type":"MAP","map":[T("parameter","content_group"),T("parameterValue","{{DLV - content_group}}")]}]}],
  "firingTriggerId":[INIT],"tagFiringOption":"ONCE_PER_EVENT"})
tags.append({"accountId":"0","containerId":"0","tagId":nid(),"name":"Conversion Linker","type":"gclidw",
  "parameter":[B("enableCrossDomain",False),B("enableUrlPassthrough",True),B("enableCookieOverrides",False)],"firingTriggerId":[ALL_PAGES],"tagFiringOption":"ONCE_PER_EVENT"})
EVENTS={
 "generate_lead":("form_name","lead_type","company_size","interest"),
 "calendly_booking":("lead_type",),
 "calendly_open":("cta_id",),
 "scorecard_start":(),
 "scorecard_complete":("score","score_level"),
 "cta_click":("cta_id","cta_text"),
 "scroll_depth":("percent","page_type"),
 "linkedin_click":(),
 "email_click":(),
 "thank_you_view":("lead_source_form",),
}
trig={}
for ev,keys in EVENTS.items():
    trig[ev]=ce(ev)
    p=[T("eventName",ev),T("measurementIdOverride","{{CONST - GA4 Measurement ID}}")]
    if keys: p.append(params(*keys))
    tags.append({"accountId":"0","containerId":"0","tagId":nid(),"name":"GA4 - "+ev,"type":"gaawe","parameter":p,"firingTriggerId":[trig[ev]],"tagFiringOption":"ONCE_PER_EVENT"})
def ads(name,label,tr):
    tags.append({"accountId":"0","containerId":"0","tagId":nid(),"name":"Ads Conversion - "+name,"type":"awct",
      "parameter":[T("conversionId","{{CONST - Google Ads Conversion ID}}"),T("conversionLabel",label),B("enableConversionLinker",True),B("enableProductReporting",False),
        T("conversionCookiePrefix","_gcl"),B("enableShippingData",False),B("rdp",False)],
      "firingTriggerId":[tr],"tagFiringOption":"ONCE_PER_EVENT"})
ads("Lead","{{CONST - Ads Label - Lead}}",trig["generate_lead"])
ads("Call Booked","{{CONST - Ads Label - Call Booked}}",trig["calendly_booking"])
li_consent={"consentStatus":"NEEDED","consentType":{"type":"LIST","list":[{"type":"TEMPLATE","value":"ad_storage"}]}}
li_html="""<script type="text/javascript">
_linkedin_partner_id = "{{CONST - LinkedIn Partner ID}}";
window._linkedin_data_partner_ids = window._linkedin_data_partner_ids || [];
window._linkedin_data_partner_ids.push(_linkedin_partner_id);
</script><script type="text/javascript">
(function(l) {if (!l){window.lintrk = function(a,b){window.lintrk.q.push([a,b])};window.lintrk.q=[]}
var s = document.getElementsByTagName("script")[0];var b = document.createElement("script");
b.type = "text/javascript";b.async = true;b.src = "https://snap.licdn.com/li.lms-analytics/insight.min.js";
s.parentNode.insertBefore(b, s);})(window.lintrk);
</script>"""
tags.append({"accountId":"0","containerId":"0","tagId":nid(),"name":"LinkedIn - Insight Tag","type":"html","parameter":[T("html",li_html),B("supportDocumentWrite",False)],
  "firingTriggerId":[ALL_PAGES],"tagFiringOption":"ONCE_PER_EVENT","consentSettings":li_consent})
tags.append({"accountId":"0","containerId":"0","tagId":nid(),"name":"LinkedIn - Conversion - Lead","type":"html",
  "parameter":[T("html",'<script>window.lintrk && window.lintrk("track", { conversion_id: {{CONST - LinkedIn Conversion ID - Lead}} });</script>'),B("supportDocumentWrite",False)],
  "firingTriggerId":[trig["generate_lead"]],"tagFiringOption":"ONCE_PER_EVENT","consentSettings":li_consent})
c={"exportFormatVersion":2,"exportTime":datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
 "containerVersion":{"path":"accounts/0/containers/0/versions/0","accountId":"0","containerId":"0","containerVersionId":"0",
  "container":{"path":"accounts/0/containers/0","accountId":"0","containerId":"0","name":"croaccelerate.com","publicId":"GTM-XXXXXXX","usageContext":["WEB"],
    "features":{"supportUserPermissions":True,"supportEnvironments":True,"supportWorkspaces":True,"supportGtagConfigs":False,"supportBuiltInVariables":True,"supportClients":False,"supportFolders":True,"supportTags":True,"supportTemplates":True,"supportTriggers":True,"supportVariables":True,"supportVersions":True,"supportZones":True,"supportTransformations":False},"tagManagerUrl":""},
  "tag":tags,"trigger":triggers,"variable":variables,
  "builtInVariable":[{"accountId":"0","containerId":"0","type":t,"name":n} for t,n in [("PAGE_URL","Page URL"),("PAGE_HOSTNAME","Page Hostname"),("PAGE_PATH","Page Path"),("REFERRER","Referrer"),("EVENT","Event")]],
  "fingerprint":"0"}}
json.dump(c,open("GTM-croaccelerate-container.json","w"),indent=2)
print(len(tags),"tags",len(triggers),"triggers",len(variables),"variables")
