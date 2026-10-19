using System.Globalization;
using System.Text;
using System.Text.Json;
using Vortice.DirectWrite;

namespace HangyeolCode.RenderWindows;

/// <summary>
/// Checks that DirectWrite moves Hangul by the per-ppem shifts in data/hints*.json.
///
/// The Hangul glyphs carry only the shift program, so rendering them with grid fitting on
/// and off differs by exactly that shift. The check compares the ink centroid of about 300
/// syllables in both renders (grayscale, natural symmetric) at each size and weight.
/// </summary>
internal static class HintCheck
{
    public const double Tolerance = 0.04; // px

    private static readonly (string Name, FontWeight Weight)[] Weights =
    [
        ("Thin", FontWeight.Thin),
        ("ExtraLight", FontWeight.ExtraLight),
        ("Light", FontWeight.Light),
        ("Regular", FontWeight.Normal),
        ("Medium", FontWeight.Medium),
        ("SemiBold", FontWeight.SemiBold),
        ("Bold", FontWeight.Bold),
        ("ExtraBold", FontWeight.ExtraBold),
    ];

    /// <summary>Every 37th Hangul syllable, 40 to a line.</summary>
    private static readonly string Syllables = string.Join("\n",
        Enumerable.Range(0, (0xD7A3 - 0xAC00) / 37 + 1)
            .Select(i => (char)(0xAC00 + i * 37))
            .Chunk(40)
            .Select(chunk => new string(chunk)));

    public static int Run(DWriteRenderer renderer, IEnumerable<Family> families, string hintsDir, string outDir, bool strict)
    {
        var report = new StringBuilder("family\tweight\tppem\texpected_px\tmeasured_px\tok\n");
        int checkedCount = 0;
        int mismatches = 0;
        foreach (Family family in families)
        {
            string path = Path.Combine(hintsDir, family.HintTable);
            if (!File.Exists(path))
            {
                Console.WriteLine($"hint check: {path} not found, skipping {family.Name}");
                continue;
            }
            var table = JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, double>>>(File.ReadAllText(path))!;
            foreach ((string weightName, FontWeight weight) in Weights)
            {
                if (!table.TryGetValue(weightName, out var shifts) || !renderer.Has(family.Name, weight))
                {
                    continue;
                }
                foreach ((string ppemText, double expected) in shifts.OrderBy(kv => int.Parse(kv.Key, CultureInfo.InvariantCulture)))
                {
                    int ppem = int.Parse(ppemText, CultureInfo.InvariantCulture);
                    RgbImage hinted = renderer.Render(Syllables, family.Name, weight, ppem, RenderMode.Grayscale, GridFitMode.Enabled);
                    RgbImage plain = renderer.Render(Syllables, family.Name, weight, ppem, RenderMode.Grayscale, GridFitMode.Disabled);
                    double measured = Centroid(plain) - Centroid(hinted); // positive: hinting moved Hangul up
                    bool ok = Math.Abs(measured - expected) <= Tolerance;
                    checkedCount++;
                    mismatches += ok ? 0 : 1;
                    report.Append(CultureInfo.InvariantCulture,
                        $"{family.Name}\t{weightName}\t{ppem}\t{expected:+0.000;-0.000;0.000}\t{measured:+0.000;-0.000;0.000}\t{(ok ? "yes" : "NO")}\n");
                }
            }
        }
        File.WriteAllText(Path.Combine(outDir, "hint-check.tsv"), report.ToString());
        Console.WriteLine($"hint check: {checkedCount} sizes checked, {mismatches} off by more than {Tolerance} px (hint-check.tsv)");
        return strict && mismatches > 0 ? 1 : 0;
    }

    /// <summary>Coverage-weighted mean row of the ink, in pixels from the top.</summary>
    private static double Centroid(RgbImage image)
    {
        double weighted = 0;
        double total = 0;
        for (int y = 0; y < image.Height; y++)
        {
            for (int x = 0; x < image.Width; x++)
            {
                double coverage = image.Coverage(x, y);
                weighted += coverage * y;
                total += coverage;
            }
        }
        return total > 0 ? weighted / total : 0;
    }
}
