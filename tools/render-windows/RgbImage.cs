using System.IO.Compression;

namespace HangyeolCode.RenderWindows;

/// <summary>An 8-bit RGB image with the few operations the sample sheets need.</summary>
internal sealed class RgbImage
{
    public RgbImage(int width, int height, byte fill = 255)
    {
        Width = width;
        Height = height;
        Pixels = new byte[width * height * 3];
        Array.Fill(Pixels, fill);
    }

    public int Width { get; }

    public int Height { get; }

    public byte[] Pixels { get; }

    public void Set(int x, int y, byte r, byte g, byte b)
    {
        int i = (y * Width + x) * 3;
        Pixels[i] = r;
        Pixels[i + 1] = g;
        Pixels[i + 2] = b;
    }

    /// <summary>Ink coverage 0..1 of a pixel: how far it is from white, averaged over the channels.</summary>
    public double Coverage(int x, int y)
    {
        int i = (y * Width + x) * 3;
        return (765 - Pixels[i] - Pixels[i + 1] - Pixels[i + 2]) / 765.0;
    }

    public void Blit(RgbImage source, int left, int top)
    {
        for (int y = 0; y < source.Height && top + y < Height; y++)
        {
            Array.Copy(source.Pixels, y * source.Width * 3, Pixels, ((top + y) * Width + left) * 3, Math.Min(source.Width, Width - left) * 3);
        }
    }

    public void FillRect(int left, int top, int width, int height, byte value)
    {
        for (int y = top; y < top + height; y++)
        {
            Array.Fill(Pixels, value, (y * Width + left) * 3, width * 3);
        }
    }

    /// <summary>Nearest-neighbour enlargement, so every rendered pixel stays visible.</summary>
    public RgbImage Zoom(int factor)
    {
        var result = new RgbImage(Width * factor, Height * factor);
        for (int y = 0; y < result.Height; y++)
        {
            for (int x = 0; x < result.Width; x++)
            {
                int s = ((y / factor) * Width + x / factor) * 3;
                result.Set(x, y, Pixels[s], Pixels[s + 1], Pixels[s + 2]);
            }
        }
        return result;
    }

    public void SavePng(string path)
    {
        using var raw = new MemoryStream();
        using (var zlib = new ZLibStream(raw, CompressionLevel.SmallestSize, leaveOpen: true))
        {
            for (int y = 0; y < Height; y++)
            {
                zlib.WriteByte(0);
                zlib.Write(Pixels, y * Width * 3, Width * 3);
            }
        }
        using var file = File.Create(path);
        file.Write([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
        var header = new byte[13];
        WriteBigEndian(header, 0, (uint)Width);
        WriteBigEndian(header, 4, (uint)Height);
        header[8] = 8; // bit depth
        header[9] = 2; // RGB
        WriteChunk(file, "IHDR", header);
        WriteChunk(file, "IDAT", raw.ToArray());
        WriteChunk(file, "IEND", []);
    }

    private static void WriteChunk(Stream stream, string type, byte[] data)
    {
        var length = new byte[4];
        WriteBigEndian(length, 0, (uint)data.Length);
        stream.Write(length);
        byte[] typeBytes = System.Text.Encoding.ASCII.GetBytes(type);
        stream.Write(typeBytes);
        stream.Write(data);
        var crc = new byte[4];
        WriteBigEndian(crc, 0, Crc32(typeBytes, data));
        stream.Write(crc);
    }

    private static void WriteBigEndian(byte[] buffer, int offset, uint value)
    {
        buffer[offset] = (byte)(value >> 24);
        buffer[offset + 1] = (byte)(value >> 16);
        buffer[offset + 2] = (byte)(value >> 8);
        buffer[offset + 3] = (byte)value;
    }

    private static readonly uint[] CrcTable = Enumerable.Range(0, 256).Select(n =>
    {
        uint c = (uint)n;
        for (int k = 0; k < 8; k++)
        {
            c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
        }
        return c;
    }).ToArray();

    private static uint Crc32(byte[] type, byte[] data)
    {
        uint c = 0xFFFFFFFF;
        foreach (byte b in type.Concat(data))
        {
            c = CrcTable[(c ^ b) & 0xFF] ^ (c >> 8);
        }
        return c ^ 0xFFFFFFFF;
    }
}
