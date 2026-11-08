// PHOENIX-001 REA validation fixture (harmless, managed PE).
// Compiled with the in-box .NET Framework csc.exe so the artifact is a real
// PE/CLI assembly that REA's managed-static provider can inspect without
// loading or executing it.

using System;
using System.Text;

public static class ReaProbe
{
    public const string Marker = "phoenix-001-rea-validation-marker";

    public static string Digest(string payload)
    {
        using (var sha = System.Security.Cryptography.SHA256.Create())
        {
            var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(payload));
            var sb = new StringBuilder(bytes.Length * 2);
            foreach (var b in bytes) sb.Append(b.ToString("x2"));
            return sb.ToString();
        }
    }

    public static string Classify(int value)
    {
        if (value < 0) return "negative";
        if (value == 0) return "zero";
        return "positive";
    }

    public static void Main()
    {
        Console.WriteLine(Digest("phoenix-001"));
        Console.WriteLine(Classify(-1) + "," + Classify(0) + "," + Classify(1));
    }
}
