using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;
using Vortice.DirectWrite;

namespace HangyeolCode.RenderWindows;

/// <summary>A built family: its name, its file name stem and its Hangul shift table.</summary>
internal sealed record Family(string Name, string Stem, string HintTable)
{
    public static readonly Family[] All =
    [
        new("Hangyeol Code", "HangyeolCode", "hints.json"),
        new("Hangyeol Code Narrow", "HangyeolCodeNarrow", "hints-narrow.json"),
    ];
}

/// <summary>
/// Renders Hangyeol Code with DirectWrite on Windows: README-style sample sheets in ClearType,
/// grayscale and GDI classic modes, and a check that the per-ppem Hangul hints take effect.
/// </summary>
internal static class Program
{
    private const string Usage = """
        Usage: render-windows [--fonts DIR] [--out DIR] [--hints DIR] [--probe DIR] [--sizes 11,14,18]
                              [--zoom 5] [--no-hint-check] [--strict]

          --fonts DIR       TTF files to load without installing them (default: fonts/ttf)
          --out DIR         where PNGs, hint-check.tsv and info.json go (default: renders)
          --hints DIR       folder with hints.json and hints-narrow.json (default: data)
          --probe DIR       probe fonts from scripts/make_hint_probe.py (default: tools/render-windows/probe)
          --sizes LIST      pixel sizes of the sample sheets (default: 11,14,18)
          --zoom N          enlargement of the zoomed sheets (default: 5)
          --no-hint-check   only render the sample sheets (no Hangul check, no probe)
          --strict          exit 1 when a measured Hangul shift misses its table value
        """;

    private const string SampleText = "if (상태 == \"완료\") { return [결과]; }\n// ※ 한글 주석 ★ ① ㈜ ½ →  ";
    private const byte Background = 240;
    private const int Gap = 16;

    private static int Main(string[] args)
    {
        var options = new Dictionary<string, string>
        {
            ["--fonts"] = "fonts/ttf",
            ["--out"] = "renders",
            ["--hints"] = "data",
            ["--probe"] = "tools/render-windows/probe",
            ["--sizes"] = "11,14,18",
            ["--zoom"] = "5",
        };
        var flags = new HashSet<string>();
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] is "--no-hint-check" or "--strict")
            {
                flags.Add(args[i]);
            }
            else if (options.ContainsKey(args[i]) && i + 1 < args.Length)
            {
                options[args[i]] = args[++i];
            }
            else
            {
                Console.Error.WriteLine(Usage);
                return 2;
            }
        }
        if (!OperatingSystem.IsWindows())
        {
            Console.Error.WriteLine("render-windows needs Windows: it renders with DirectWrite.");
            return 2;
        }

        int[] sizes = options["--sizes"].Split(',').Select(s => int.Parse(s, CultureInfo.InvariantCulture)).ToArray();
        int zoom = int.Parse(options["--zoom"], CultureInfo.InvariantCulture);
        string outDir = options["--out"];
        Directory.CreateDirectory(outDir);

        using var renderer = new DWriteRenderer(options["--fonts"]);
        var families = Family.All.Where(f => renderer.Has(f.Name, FontWeight.Normal)).ToList();
        var written = new List<string>();
        foreach (Family family in families)
        {
            foreach (RenderMode mode in RenderMode.All)
            {
                foreach ((int factor, string suffix) in new[] { (zoom, ""), (1, "-1x") })
                {
                    string name = $"{family.Stem}-{mode.Name}{suffix}.png";
                    SampleSheet(renderer, family, mode, sizes, factor).SavePng(Path.Combine(outDir, name));
                    written.Add(name);
                }
            }
        }
        Console.WriteLine($"Wrote {written.Count} sample sheets to {outDir}");

        int status = 0;
        if (!flags.Contains("--no-hint-check"))
        {
            HintProbe.Run(options["--probe"], outDir);
            status = HintCheck.Run(renderer, families, options["--hints"], outDir, flags.Contains("--strict"));
        }
        WriteInfo(Path.Combine(outDir, "info.json"), renderer, sizes, zoom, written);
        return status;
    }

    /// <summary>Two sample lines per size on white boxes, with the size beside each box.</summary>
    private static RgbImage SampleSheet(DWriteRenderer renderer, Family family, RenderMode mode, int[] sizes, int zoom)
    {
        var rows = sizes.Select(size =>
        {
            RgbImage text = renderer.Render(SampleText, family.Name, FontWeight.Normal, size, mode);
            RgbImage label = renderer.Render($"{size}px", "Hangyeol Code", FontWeight.Normal, zoom > 1 ? 28 : 12, RenderMode.Grayscale);
            return (Text: zoom > 1 ? text.Zoom(zoom) : text, Label: label);
        }).ToList();
        int labelWidth = rows.Max(r => r.Label.Width) + 2 * Gap;
        int width = labelWidth + rows.Max(r => r.Text.Width) + Gap;
        int height = rows.Sum(r => r.Text.Height + Gap) + Gap;
        var sheet = new RgbImage(width, height, Background);
        int top = Gap;
        foreach ((RgbImage text, RgbImage label) in rows)
        {
            sheet.Blit(text, labelWidth, top);
            int labelTop = top + (text.Height - label.Height) / 2;
            for (int y = 0; y < label.Height; y++)
            {
                for (int x = 0; x < label.Width; x++)
                {
                    byte value = (byte)Math.Round(Background * (1 - label.Coverage(x, y)));
                    sheet.Set(Gap + x, labelTop + y, value, value, value);
                }
            }
            top += text.Height + Gap;
        }
        return sheet;
    }

    /// <summary>Record what produced the images: Windows and DirectWrite versions, fonts, parameters.</summary>
    private static void WriteInfo(string path, DWriteRenderer renderer, int[] sizes, int zoom, List<string> images)
    {
        string? build = null;
        string? displayVersion = null;
        if (OperatingSystem.IsWindows())
        {
            using var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion");
            build = $"{key?.GetValue("CurrentBuild")}.{key?.GetValue("UBR")}";
            displayVersion = key?.GetValue("DisplayVersion") as string;
        }
        string dwrite = Path.Combine(Environment.SystemDirectory, "dwrite.dll");
        var info = new
        {
            generated_utc = DateTime.UtcNow.ToString("u", CultureInfo.InvariantCulture),
            os = RuntimeInformation.OSDescription,
            windows_build = build,
            windows_display_version = displayVersion,
            dwrite_version = File.Exists(dwrite) ? FileVersionInfo.GetVersionInfo(dwrite).FileVersion : null,
            rendering = new
            {
                gamma = DWriteRenderer.Gamma,
                enhanced_contrast = DWriteRenderer.EnhancedContrast,
                grayscale_enhanced_contrast = DWriteRenderer.GrayscaleEnhancedContrast,
                pixel_geometry = "RGB",
                modes = RenderMode.All.Select(m => new { m.Name, mode = m.Mode.ToString(), cleartype = m.ClearType, gdi_compatible_layout = m.GdiCompatible }),
            },
            sizes,
            zoom,
            fonts = renderer.FontFiles,
            images,
        };
        File.WriteAllText(path, JsonSerializer.Serialize(info, new JsonSerializerOptions { WriteIndented = true }));
    }
}
