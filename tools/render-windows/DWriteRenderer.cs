using SharpGen.Runtime;
using Vortice.DCommon;
using Vortice.DirectWrite;

namespace HangyeolCode.RenderWindows;

/// <summary>How text is rasterized: a DirectWrite rendering mode with ClearType or grayscale.</summary>
internal sealed record RenderMode(string Name, RenderingMode1 Mode, bool ClearType, bool GdiCompatible)
{
    public static readonly RenderMode ClearTypeNatural = new("cleartype", RenderingMode1.NaturalSymmetric, true, false);
    public static readonly RenderMode Grayscale = new("grayscale", RenderingMode1.NaturalSymmetric, false, false);
    public static readonly RenderMode GdiClassic = new("gdi-classic", RenderingMode1.GdiClassic, true, true);

    public static readonly RenderMode[] All = [ClearTypeNatural, Grayscale, GdiClassic];
}

/// <summary>
/// Renders text with DirectWrite from font files that are not installed: the fonts are put in
/// a private font set, laid out with IDWriteTextLayout (so ligatures apply) and drawn into an
/// offscreen GDI-interop bitmap. Rendering parameters are explicit, so the output does not
/// depend on the ClearType settings of the account the agent runs as.
/// </summary>
internal sealed class DWriteRenderer : IDisposable
{
    // DirectWrite's default rendering parameters (gamma 1.8, contrast 0.5, ClearType level 1.0).
    public const float Gamma = 1.8f;
    public const float EnhancedContrast = 0.5f;
    public const float GrayscaleEnhancedContrast = 1.0f;
    private const int Padding = 4;

    private readonly IDWriteFactory5 _factory;
    private readonly IDWriteFontCollection1 _collection;
    private readonly IDWriteGdiInterop _gdiInterop;

    public DWriteRenderer(string fontDir)
    {
        _factory = DWrite.DWriteCreateFactory<IDWriteFactory5>(FactoryType.Isolated);
        using IDWriteFontSetBuilder1 builder = _factory.CreateFontSetBuilder();
        foreach (string path in Directory.GetFiles(fontDir, "*.ttf").Order())
        {
            using IDWriteFontFile file = _factory.CreateFontFileReference(Path.GetFullPath(path), null);
            builder.AddFontFile(file);
            FontFiles.Add(Path.GetFileName(path));
        }
        if (FontFiles.Count == 0)
        {
            throw new FileNotFoundException($"No .ttf files in {fontDir}");
        }
        using IDWriteFontSet fontSet = builder.CreateFontSet();
        _collection = _factory.CreateFontCollectionFromFontSet(fontSet);
        _gdiInterop = _factory.GdiInterop;
    }

    public List<string> FontFiles { get; } = [];

    /// <summary>Whether the private collection has this family at this weight.</summary>
    public bool Has(string family, FontWeight weight)
    {
        if (!_collection.FindFamilyName(family, out uint index))
        {
            return false;
        }
        using IDWriteFontFamily fontFamily = _collection.GetFontFamily(index);
        using IDWriteFont font = fontFamily.GetFirstMatchingFont(weight, FontStretch.Normal, FontStyle.Normal);
        return font.Weight == weight;
    }

    /// <summary>Render <paramref name="text"/> (lines separated by \n) black on white.</summary>
    public RgbImage Render(string text, string family, FontWeight weight, float sizePx, RenderMode mode,
        GridFitMode gridFit = GridFitMode.Default)
    {
        using IDWriteTextFormat format = _factory.CreateTextFormat(
            family, _collection, weight, FontStyle.Normal, FontStretch.Normal, sizePx, "ko-kr");
        using IDWriteTextLayout layout = mode.GdiCompatible
            ? _factory.CreateGdiCompatibleTextLayout(text, (uint)text.Length, format, 100000, 100000, 1f, null, false)
            : _factory.CreateTextLayout(text, format, 100000, 100000);
        TextMetrics metrics = layout.Metrics;
        int width = (int)Math.Ceiling(metrics.WidthIncludingTrailingWhitespace) + 2 * Padding;
        int height = (int)Math.Ceiling(metrics.Height) + 2 * Padding;

        using IDWriteBitmapRenderTarget target = _gdiInterop.CreateBitmapRenderTarget(IntPtr.Zero, (uint)width, (uint)height);
        target.PixelsPerDip = 1f;
        using (IDWriteBitmapRenderTarget1 target1 = target.QueryInterface<IDWriteBitmapRenderTarget1>())
        {
            target1.TextAntialiasMode = mode.ClearType ? TextAntialiasMode.Cleartype : TextAntialiasMode.Grayscale;
        }
        IntPtr dc = target.MemoryDC;
        Gdi.FillWhite(dc, width, height);

        using IDWriteRenderingParams3 parameters = _factory.CreateCustomRenderingParams(
            Gamma, EnhancedContrast, GrayscaleEnhancedContrast, mode.ClearType ? 1f : 0f,
            PixelGeometry.Rgb, mode.Mode, gridFit);
        using var renderer = new GlyphRunRenderer(target, parameters);
        layout.Draw(IntPtr.Zero, renderer, Padding, Padding);
        return Gdi.Read(dc);
    }

    public void Dispose()
    {
        _gdiInterop.Dispose();
        _collection.Dispose();
        _factory.Dispose();
    }

    /// <summary>Draws each glyph run the layout produces onto the bitmap render target.</summary>
    private sealed class GlyphRunRenderer(IDWriteBitmapRenderTarget target, IDWriteRenderingParams parameters)
        : TextRendererBase
    {
        public override void DrawGlyphRun(IntPtr clientDrawingContext, float baselineOriginX, float baselineOriginY,
            MeasuringMode measuringMode, GlyphRun glyphRun, GlyphRunDescription glyphRunDescription,
            IUnknown? clientDrawingEffect)
        {
            target.DrawGlyphRun(baselineOriginX, baselineOriginY, measuringMode, glyphRun, parameters, 0x000000);
        }
    }
}
