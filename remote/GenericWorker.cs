using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;using System.Threading;using System.Runtime.InteropServices;using System.Web.Script.Serialization;using LabVIEWAutomation;
public static class GenericWorker {
 public static string LastVersion="";
 public static object Typed(object input,string type){
  if(type=="bool")return Convert.ToBoolean(input);
  if(type=="int32")return Convert.ToInt32(input);
  if(type.StartsWith("array{")){
   IEnumerable seq=input as IEnumerable;if(seq==null)throw new Exception("Array input is not enumerable");
   if(type=="array{int32}"){var a=new List<int>();foreach(object x in seq)a.Add(Convert.ToInt32(x));return a.ToArray();}
   var b=new List<double>();foreach(object x in seq)b.Add(Convert.ToDouble(x));return b.ToArray();
  }
  return Convert.ToDouble(input);
 }
 public static string RunCaseJson(string path,string[] names,object[] inputs,string[] types,string[] outputs){
  Application app=null;VirtualInstrument vi=null;
  try{
   app=new Application();LastVersion=app.Version;vi=app.GetVIReference(path,"",false,0);
   if(vi.ExecState==ExecStateEnum.eBad)throw new Exception("VI is not executable");
   for(int i=0;i<names.Length;i++)vi.SetControlValue(names[i],Typed(inputs[i],types[i]));
   vi.Run(true);var watch=Stopwatch.StartNew();
   while(vi.ExecState==ExecStateEnum.eRunTopLevel || vi.ExecState==ExecStateEnum.eRunning){
    if(watch.ElapsedMilliseconds>10000){vi.Abort();throw new Exception("VI exceeded10s execution limit; only this generated VI was aborted");}Thread.Sleep(5);
   }
   if(vi.ExecState!=ExecStateEnum.eIdle)throw new Exception("Unexpected final VI execution state");
   var result=new Dictionary<string,object>();foreach(string label in outputs)result[label]=vi.GetControlValue(label);vi.SaveInstrument(path,false,false);
   return new JavaScriptSerializer(){MaxJsonLength=4000000}.Serialize(result);
  }finally{if(vi!=null)Marshal.ReleaseComObject(vi);if(app!=null)Marshal.ReleaseComObject(app);}
 }
}
