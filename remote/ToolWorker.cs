using System;using System.IO;using LabVIEWAutomation;
public static class ToolWorker {
 public static double RunVI(string path,string task,double raw,double secondary){
 Application app=new Application();VirtualInstrument vi=app.GetVIReference(path,"",false,0);string input=task=="offset_correction"?"Offset":"Scale",output=task=="offset_correction"?"CorrectedCurrent":"Current";
 vi.SetControlValue("RawCurrent",raw);vi.SetControlValue(input,secondary);vi.Run(false);double actual=Convert.ToDouble(vi.GetControlValue(output));double expected=task=="offset_correction"?raw-secondary:raw*secondary;if(Math.Abs(actual-expected)>1e-9*Math.Max(1,Math.Abs(expected)))throw new Exception("Numerical verification failed");vi.SaveInstrument(path,false,false);return actual;
 }
}
