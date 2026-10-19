using System.Runtime.InteropServices;

namespace HangyeolCode.RenderWindows;

/// <summary>The few GDI calls needed to clear and read the DirectWrite bitmap render target.</summary>
internal static class Gdi
{
    private const uint ObjBitmap = 7;
    private const uint Whiteness = 0x00FF0062;

    [StructLayout(LayoutKind.Sequential)]
    private struct Bitmap
    {
        public int Type;
        public int Width;
        public int Height;
        public int WidthBytes;
        public ushort Planes;
        public ushort BitsPixel;
        public IntPtr Bits;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BitmapInfoHeader
    {
        public uint Size;
        public int Width;
        public int Height;
        public ushort Planes;
        public ushort BitCount;
        public uint Compression;
        public uint SizeImage;
        public int XPelsPerMeter;
        public int YPelsPerMeter;
        public uint ClrUsed;
        public uint ClrImportant;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct DibSection
    {
        public Bitmap Bm;
        public BitmapInfoHeader Bmih;
        public uint Bitfield0;
        public uint Bitfield1;
        public uint Bitfield2;
        public IntPtr Section;
        public uint Offset;
    }

    [DllImport("gdi32.dll")]
    private static extern IntPtr GetCurrentObject(IntPtr hdc, uint type);

    [DllImport("gdi32.dll", EntryPoint = "GetObjectW")]
    private static extern int GetObject(IntPtr handle, int size, out DibSection section);

    [DllImport("gdi32.dll")]
    private static extern bool PatBlt(IntPtr hdc, int x, int y, int width, int height, uint rop);

    public static void FillWhite(IntPtr hdc, int width, int height)
    {
        if (!PatBlt(hdc, 0, 0, width, height, Whiteness))
        {
            throw new InvalidOperationException("PatBlt failed");
        }
    }

    /// <summary>Copy the 32-bit DIB selected into <paramref name="hdc"/> into an RGB image.</summary>
    public static RgbImage Read(IntPtr hdc)
    {
        IntPtr bitmap = GetCurrentObject(hdc, ObjBitmap);
        if (GetObject(bitmap, Marshal.SizeOf<DibSection>(), out DibSection dib) == 0 || dib.Bm.Bits == IntPtr.Zero)
        {
            throw new InvalidOperationException("Could not read the render target bitmap");
        }
        int width = dib.Bm.Width;
        int height = Math.Abs(dib.Bm.Height);
        bool topDown = dib.Bmih.Height < 0;
        var row = new byte[dib.Bm.WidthBytes];
        var image = new RgbImage(width, height);
        for (int y = 0; y < height; y++)
        {
            int sourceRow = topDown ? y : height - 1 - y;
            Marshal.Copy(dib.Bm.Bits + sourceRow * dib.Bm.WidthBytes, row, 0, row.Length);
            for (int x = 0; x < width; x++)
            {
                // BGRA in memory.
                image.Set(x, y, row[x * 4 + 2], row[x * 4 + 1], row[x * 4]);
            }
        }
        return image;
    }
}
