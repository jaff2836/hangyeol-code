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
/// syllables in both renders (grayscale, natural symmetric, linear coverage, baselines on
/// whole pixels) at each size and weight.
///
/// DirectWrite quantizes vertical edges, which also changes the thickness of thin strokes, so
/// the centroid of real text strays from the shift by up to about half a pixel at some sizes
/// (most in Thin). This is a report; the probe fonts (HintProbe) are the pass/fail test.
/// </summary>
internal static class HintCheck
{
    private const double Still = 0.02; // px; smaller moves count as none

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

    public static void Run(DWriteRenderer renderer, IEnumerable<Family> families, string hintsDir, string outDir)
    {
        var report = new StringBuilder("family\tweight\tppem\texpected_px\tmeasured_px\tsame_direction\n");
        int shifted = 0;
        int sameDirection = 0;
        var errors = new List<double>();
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
                    RgbImage hinted = renderer.Render(Syllables, family.Name, weight, ppem, RenderMode.Grayscale,
                        GridFitMode.Enabled, linear: true, snapBaseline: true);
                    RgbImage plain = renderer.Render(Syllables, family.Name, weight, ppem, RenderMode.Grayscale,
                        GridFitMode.Disabled, linear: true, snapBaseline: true);
                    double measured = Centroid(plain) - Centroid(hinted); // positive: hinting moved Hangul up
                    bool same = expected == 0 ? Math.Abs(measured) <= Still : measured * Math.Sign(expected) > Still;
                    shifted += expected == 0 ? 0 : 1;
                    sameDirection += expected != 0 && same ? 1 : 0;
                    errors.Add(measured - expected);
                    report.Append(CultureInfo.InvariantCulture,
                        $"{family.Name}\t{weightName}\t{ppem}\t{expected:+0.000;-0.000;0.000}\t{measured:+0.000;-0.000;0.000}\t{(same ? "yes" : "no")}\n");
                }
            }
        }
        File.WriteAllText(Path.Combine(outDir, "hint-check.tsv"), report.ToString());
        if (errors.Count > 0)
        {
            Console.WriteLine(string.Create(CultureInfo.InvariantCulture,
                $"hangul: {errors.Count} sizes, {sameDirection} of {shifted} shifted sizes move the right way; measured minus table: mean {errors.Average():+0.000;-0.000;0.000} px, mean |error| {errors.Average(Math.Abs):0.000} px (hint-check.tsv)"));
        }
    }

    /// <summary>Coverage-weighted mean row of the ink, in pixels from the top.</summary>
    public static double Centroid(RgbImage image)
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
