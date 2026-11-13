using System;using System.IO;using System.Linq;using System.Collections;using System.Collections.Generic;using System.Diagnostics;using System.Threading;using System.Runtime.InteropServices;using System.Web.Script.Serialization;using LabVIEWAutomation;
public static class GuiWorker {
 static JavaScriptSerializer J=new JavaScriptSerializer(){MaxJsonLength=5000000};
 static Dictionary<string,object> Obj(object x){return (Dictionary<string,object>)x;}
 static object[] Arr(object x){return ((IEnumerable)x).Cast<object>().ToArray();}
 static bool Equal(object a,object b){
  if(a is bool || b is bool)return a is bool && b is bool && (bool)a==(bool)b;
  if(a is IEnumerable && !(a is string) || b is IEnumerable && !(b is string)){if(!(a is IEnumerable)||!(b is IEnumerable))return false;object[] x=Arr(a),y=Arr(b);return x.Length==y.Length && x.Zip(y,(v,w)=>Equal(v,w)).All(v=>v);}
  double u=Convert.ToDouble(a),v2=Convert.ToDouble(b);return !double.IsNaN(u)&&!double.IsInfinity(u)&&Math.Abs(u-v2)<=1e-8*Math.Max(1,Math.Abs(v2));
 }
 static Dictionary<string,object> Read(VirtualInstrument vi,string[] outputs){var r=new Dictionary<string,object>();foreach(string n in outputs)r[n]=vi.GetControlValue(n);return r;}
 static bool Matches(Dictionary<string,object> actual,Dictionary<string,object> target,bool lowerBound){foreach(var p in target){if(!actual.ContainsKey(p.Key))return false;object a=actual[p.Key];bool numeric=!(a is bool)&&!(a is IEnumerable);if(lowerBound&&numeric){if(Convert.ToDouble(a)<Convert.ToDouble(p.Value))return false;}else if(!Equal(a,p.Value))return false;}return true;}
 static bool IsRunning(VirtualInstrument vi){return vi.ExecState==ExecStateEnum.eRunning||vi.ExecState==ExecStateEnum.eRunTopLevel;}
 static void Guard(VirtualInstrument vi,Stopwatch total){if(total.ElapsedMilliseconds>18000){if(IsRunning(vi))vi.Abort();throw new Exception("GUI case exceeded18s; only this generated VI was aborted");}}
 static Dictionary<string,object> Wait(VirtualInstrument vi,string[] outputs,Dictionary<string,object> target,bool lower,Stopwatch total){var sw=Stopwatch.StartNew();while(sw.ElapsedMilliseconds<4500){Guard(vi,total);var r=Read(vi,outputs);if(Matches(r,target,lower))return r;Thread.Sleep(8);}throw new Exception("GUI wait/assertion timed out: "+J.Serialize(target));}
 static int Signal(VirtualInstrument helper,string target,string name){helper.SetControlValue("TargetPath",target);helper.SetControlValue("ControlName",name);helper.Run(false);int code=Convert.ToInt32(helper.GetControlValue("Code"));if(Convert.ToBoolean(helper.GetControlValue("Error"))||code!=0)throw new Exception("Value(Signaling) helper failed: "+name+" code="+code);return code;}
 static void Capture(VirtualInstrument vi,VirtualInstrument helper,string path,string dir){
  object image,colors,bounds;vi.GetPanelImage(false,24,out image,out colors,out bounds);var rect=Arr(bounds).Select(Convert.ToInt32).ToArray();
  File.WriteAllBytes(Path.Combine(dir,"front-panel.raw"),(byte[])image);File.WriteAllText(Path.Combine(dir,"front-panel-meta.json"),J.Serialize(new{width=rect[2]-rect[0],height=rect[3]-rect[1],depth=24}));
  helper.SetControlValue("TargetPath",path);helper.Run(false);int error=Convert.ToInt32(helper.GetControlValue("Code"));if(error!=0||Convert.ToBoolean(helper.GetControlValue("Error")))throw new Exception("Native block diagram capture failed code="+error);
  File.WriteAllBytes(Path.Combine(dir,"block-diagram.raw"),(byte[])helper.GetControlValue("Image"));File.WriteAllText(Path.Combine(dir,"block-diagram-meta.json"),J.Serialize(new{width=Convert.ToInt32(helper.GetControlValue("Width")),height=Convert.ToInt32(helper.GetControlValue("Height")),depth=Convert.ToInt32(helper.GetControlValue("Depth"))}));
 }
 public static string RunCaseJson(string path,string tools,string request,int index){
  Application app=null;VirtualInstrument vi=null,signal=null,capture=null;var total=Stopwatch.StartNew();
  try{
   var req=Obj(J.DeserializeObject(request));var test=Obj(Arr(req["tests"])[index]);var inputs=Obj(test["inputs"]);var inputTypes=Obj(req["input_types"]);var expected=Obj(test["expected"]);string[] outputs=expected.Keys.ToArray();string[] buttons=Arr(req["gui_buttons"]).Select(Convert.ToString).ToArray();
   app=new Application();GenericWorker.LastVersion=app.Version;vi=app.GetVIReference(path,"",false,0);if(vi.ExecState==ExecStateEnum.eBad)throw new Exception("GUI VI is not executable");
   foreach(var p in inputs)vi.SetControlValue(p.Key,GenericWorker.Typed(p.Value,Convert.ToString(inputTypes[p.Key])));
   foreach(string name in buttons)vi.SetControlValue(name,false);vi.SetControlValue("NI_Ready",false);vi.SetControlValue("NI_GuiEventCount",0);vi.SetControlValue("NI_TimeoutCount",0);
   signal=app.GetVIReference(Path.Combine(tools,"SignalGuiBoolean.vi"),"",false,0);capture=app.GetVIReference(Path.Combine(tools,"CaptureGuiDiagram.vi"),"",false,0);
   total.Restart();vi.FPWinOpen=true;vi.Run(true);var ready=Stopwatch.StartNew();while(!Convert.ToBoolean(vi.GetControlValue("NI_Ready"))){Guard(vi,total);if(ready.ElapsedMilliseconds>3000)throw new Exception("GUI loop did not become ready");Thread.Sleep(5);}Thread.Sleep(15);
   var evidence=new List<object>();int interval=Convert.ToInt32(Arr(req["gui_intervals"])[index]);
   foreach(object actionObj in Arr(test["actions"])){
    Guard(vi,total);var action=Obj(actionObj);
    if(action.ContainsKey("event")){
     string name=Convert.ToString(action["event"]);if(!buttons.Contains(name))throw new Exception("Unknown GUI button");int before=Convert.ToInt32(vi.GetControlValue("NI_GuiEventCount"));int code=Signal(signal,path,name);var sw=Stopwatch.StartNew();while(Convert.ToInt32(vi.GetControlValue("NI_GuiEventCount"))<=before){Guard(vi,total);if(sw.ElapsedMilliseconds>3500)throw new Exception("GUI Value Change frame did not handle "+name);Thread.Sleep(5);}Thread.Sleep(12);if(Convert.ToBoolean(vi.GetControlValue(name)))throw new Exception("GUI pushbutton did not reset: "+name);evidence.Add(new{button=name,signal_error=code,event_count=vi.GetControlValue("NI_GuiEventCount"),actual=Read(vi,outputs)});
    }else if(action.ContainsKey("wait")){var r=Wait(vi,outputs,Obj(action["wait"]),true,total);evidence.Add(new{wait=action["wait"],actual=r});}
    else if(action.ContainsKey("expect")){var r=Wait(vi,outputs,Obj(action["expect"]),false,total);evidence.Add(new{assertion=action["expect"],actual=r});}
    else if(action.ContainsKey("stable")){
     string[] fields=Arr(action["stable"]).Select(Convert.ToString).ToArray();int ticks=Convert.ToInt32(action["ticks"]);var before=Read(vi,fields);int t0=Convert.ToInt32(vi.GetControlValue("NI_TimeoutCount"));var sw=Stopwatch.StartNew();Thread.Sleep(ticks*interval+100);var after=Read(vi,fields);int delta=Convert.ToInt32(vi.GetControlValue("NI_TimeoutCount"))-t0;
     if(!Matches(after,before,false))throw new Exception("Stopped GUI outputs changed while Timeout kept firing");if(delta<ticks)throw new Exception("Timeout frame did not actually fire at configured interval");double measured=sw.Elapsed.TotalMilliseconds/delta;if(measured<interval*0.5 || measured>interval*2.0+15)throw new Exception("Timeout cadence differs from configuration");
     double[] times=Arr(vi.GetControlValue("NI_TimeoutTimes")).Select(Convert.ToDouble).ToArray();var samples=new List<double>();for(int n=Math.Max(1,times.Length-Math.Max(1,delta-1));n<times.Length;n++){double dt=times[n]-times[n-1];if(dt<0)dt+=4294967296.0;if(dt<interval*0.8||dt>interval*2+30)throw new Exception("Measured Timeout interarrival differs from configuration");samples.Add(dt);}if(samples.Count==0)throw new Exception("No native timer intervals captured");
     evidence.Add(new{stable=fields,before=before,after=after,timeout_events=delta,elapsed_ms=sw.Elapsed.TotalMilliseconds,configured_ms=interval,window_estimate_ms=measured,interval_samples_ms=samples.ToArray(),mean_interval_ms=samples.Average()});
    }else throw new Exception("Unsupported GUI test action");
   }
   while(IsRunning(vi)){Guard(vi,total);Thread.Sleep(5);}if(vi.ExecState!=ExecStateEnum.eIdle)throw new Exception("GUI did not exit normally");var actual=Read(vi,outputs);if(!Matches(actual,expected,false))throw new Exception("GUI final outputs do not match expected");vi.SaveInstrument(path,false,false);
   Capture(vi,capture,path,Path.GetDirectoryName(path));
   if(req.ContainsKey("module_files") && index==Arr(req["tests"]).Length-1){foreach(object moduleObj in Arr(req["module_files"])){
    string module=Convert.ToString(moduleObj);string modulePath=Path.Combine(Path.GetDirectoryName(path),"Modules",module);VirtualInstrument sub=null;
    try{sub=app.GetVIReference(modulePath,"",false,0);if(sub.ExecState==ExecStateEnum.eBad)throw new Exception("SubVI is not executable: "+module);sub.SaveInstrument(modulePath,false,false);string target=Path.Combine(Path.GetDirectoryName(path),"subvi-images",Path.GetFileNameWithoutExtension(module));Directory.CreateDirectory(target);Capture(sub,capture,modulePath,target);}finally{if(sub!=null)Marshal.ReleaseComObject(sub);}
   }}
   if(req.ContainsKey("typedef_files") && index==Arr(req["tests"]).Length-1){foreach(object typeObj in Arr(req["typedef_files"])){
    string file=Convert.ToString(typeObj);VirtualInstrument ctl=null;try{ctl=app.GetVIReference(Path.Combine(Path.GetDirectoryName(path),"Types",file),"",false,0);ctl.FPWinOpen=true;object raw,palette,rectangle;ctl.GetPanelImage(false,24,out raw,out palette,out rectangle);var box=Arr(rectangle).Select(Convert.ToInt32).ToArray();string destination=Path.Combine(Path.GetDirectoryName(path),"typedef-images",Path.GetFileNameWithoutExtension(file));Directory.CreateDirectory(destination);File.WriteAllBytes(Path.Combine(destination,"front-panel.raw"),(byte[])raw);File.WriteAllText(Path.Combine(destination,"front-panel-meta.json"),J.Serialize(new{width=box[2]-box[0],height=box[3]-box[1],depth=24}));}finally{if(ctl!=null)Marshal.ReleaseComObject(ctl);}
   }}return J.Serialize(new{actual=actual,gui_evidence=evidence,gui_event_count=vi.GetControlValue("NI_GuiEventCount"),timeout_count=vi.GetControlValue("NI_TimeoutCount"),gui_trace=vi.GetControlValue("NI_GuiTrace"),elapsed_ms=total.Elapsed.TotalMilliseconds});
  }finally{
   if(vi!=null){if(IsRunning(vi))vi.Abort();Marshal.ReleaseComObject(vi);}if(signal!=null)Marshal.ReleaseComObject(signal);if(capture!=null)Marshal.ReleaseComObject(capture);if(app!=null)Marshal.ReleaseComObject(app);
  }
 }
}
