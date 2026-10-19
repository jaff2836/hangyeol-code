using System.Globalization;
using System.Text;
using Vortice.DirectWrite;

namespace HangyeolCode.RenderWindows;

/// <summary>
/// Measures how far DirectWrite moves the rectangles of the probe fonts made by
/// scripts/make_hint_probe.py, whose shifts are known (Up8 +1/8 px, Up32 +1/2 px,
/// Down8 -1/8 px, Direct8 +1/8 px, None 0).
///
/// Each probe is compared with the None probe rendered the same way (works in every mode),
/// and with itself with grid fitting off (natural modes only). Coverage is linear and the
/// baseline on a whole pixel, so the centroid moves exactly as far as the outline does.
/// </summary>
internal static class HintProbe
{
    private static readonly (string Name, double Expected)[] Probes =
    [
        ("Up8", 0.125),
        ("Up32", 0.5),
        ("Down8", -0.125),
        ("Direct8", 0.125),
        ("None", 0.0),
    ];

    private const string Text = "AAAAAAAA";

    public static void Run(string probeDir, string outDir)
    {
        if (!Directory.Exists(probeDir))
        {
            Console.WriteLine($"probe: {probeDir} not found, skipping");
            return;
        }
        using var renderer = new DWriteRenderer(probeDir);
        var report = new StringBuilder("probe\tmode\tppem\texpected_px\tvs_none_px\tvs_unhinted_px\theight_px\theight_unhinted_px\n");
        var summary = new Dictionary<(string, string), List<double>>();
        foreach (RenderMode mode in RenderMode.All)
        {
            for (int ppem = 10; ppem <= 20; ppem++)
            {
                RgbImage none = Render(renderer, "None", ppem, mode, GridFitMode.Enabled);
                double noneCentroid = HintCheck.Centroid(none);
                foreach ((string name, double expected) in Probes)
                {
                    RgbImage hinted = Render(renderer, name, ppem, mode, GridFitMode.Enabled);
                    double vsNone = noneCentroid - HintCheck.Centroid(hinted);
                    string vsPlain = "";
                    string plainHeight = "";
                    if (!mode.GdiCompatible)
                    {
                        RgbImage plain = Render(renderer, name, ppem, mode, GridFitMode.Disabled);
                        vsPlain = (HintCheck.Centroid(plain) - HintCheck.Centroid(hinted)).ToString("+0.000;-0.000;0.000", CultureInfo.InvariantCulture);
                        plainHeight = InkHeight(plain).ToString("0.000", CultureInfo.InvariantCulture);
                    }
                    report.Append(CultureInfo.InvariantCulture,
                        $"{name}\t{mode.Name}\t{ppem}\t{expected:+0.000;-0.000;0.000}\t{vsNone:+0.000;-0.000;0.000}\t{vsPlain}\t{InkHeight(hinted):0.000}\t{plainHeight}\n");
                    var key = (name, mode.Name);
                    if (!summary.TryGetValue(key, out var values))
                    {
                        summary[key] = values = [];
                    }
                    values.Add(vsNone - expected);
                }
            }
        }
        File.WriteAllText(Path.Combine(outDir, "probe.tsv"), report.ToString());
        Console.WriteLine("probe: measured minus expected shift against the None probe, 10-20 ppem (probe.tsv)");
        foreach (((string name, string mode), List<double> errors) in summary)
        {
            Console.WriteLine(string.Create(CultureInfo.InvariantCulture,
                $"  {name,-8} {mode,-12} mean {errors.Average():+0.000;-0.000;0.000} px, worst {errors.MaxBy(Math.Abs):+0.000;-0.000;0.000} px"));
        }
    }

    private static RgbImage Render(DWriteRenderer renderer, string probe, int ppem, RenderMode mode, GridFitMode gridFit) =>
        renderer.Render(Text, $"Hangyeol Probe {probe}", FontWeight.Normal, ppem, mode, gridFit, linear: true, snapBaseline: true);

    /// <summary>Total coverage divided by the widest row's coverage: the rectangle's height in pixels.</summary>
    private static double InkHeight(RgbImage image)
    {
        double total = 0;
        double widest = 0;
        for (int y = 0; y < image.Height; y++)
        {
            double row = 0;
            for (int x = 0; x < image.Width; x++)
            {
                row += image.Coverage(x, y);
            }
            total += row;
            widest = Math.Max(widest, row);
        }
        return widest > 0 ? total / widest : 0;
    }
}
