using System.Security.Cryptography;
using System.Text.Json;
using Ps2IsoTools.UDF;
using Ps2IsoTools.UDF.Files;

namespace Fragmenter.IsoBridge;

internal static class Program
{
    private sealed record Verification(string Id, string Type, string IsoPath, long Offset, byte[]? Bytes, string? Sha256);

    private static int Main(string[] args)
    {
        if (args.Length != 3)
        {
            Console.Error.WriteLine("Usage: Fragmenter.IsoBridge <source.iso> <manifest.json> <output.iso>");
            return 64;
        }

        string source = Path.GetFullPath(args[0]);
        string manifestPath = Path.GetFullPath(args[1]);
        string output = Path.GetFullPath(args[2]);
        string outputDirectory = Path.GetDirectoryName(output) ?? Directory.GetCurrentDirectory();
        string token = Guid.NewGuid().ToString("N");
        string working = Path.Combine(outputDirectory, $".fragmenter-{token}.working.iso");
        string rebuilt = Path.Combine(outputDirectory, $".fragmenter-{token}.rebuilt.iso");

        try
        {
            ValidatePaths(source, manifestPath, output);
            Directory.CreateDirectory(outputDirectory);

            using JsonDocument manifest = JsonDocument.Parse(File.ReadAllText(manifestPath));
            JsonElement root = manifest.RootElement;
            if (root.GetProperty("schema_version").GetInt32() != 1)
                throw new InvalidDataException("Only Fragmenter patch manifest schema 1 is supported.");

            ValidateSource(source, root.GetProperty("source"));
            JsonElement operations = root.GetProperty("operations");
            if (operations.ValueKind != JsonValueKind.Array || operations.GetArrayLength() == 0)
                throw new InvalidDataException("The patch manifest contains no operations.");

            File.Copy(source, working, false);
            List<Verification> verifications = ApplyOperations(working, manifestPath, operations);
            using (UdfEditor editor = new(working))
                editor.Rebuild(rebuilt);

            VerifyOutput(rebuilt, verifications);
            File.Move(rebuilt, output, false);

            var report = new
            {
                schema_version = 1,
                status = "applied",
                engine = "fragmenter-udf-bridge",
                source = new { path = source, size = new FileInfo(source).Length, sha256 = HashFile(source) },
                output = new { path = output, size = new FileInfo(output).Length, sha256 = HashFile(output) },
                operations = verifications.Select(item => new
                {
                    id = item.Id,
                    type = item.Type,
                    path = item.IsoPath,
                    status = "verified"
                })
            };
            Console.WriteLine(JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
        }
        catch (Exception exception)
        {
            var error = new { status = "refused", error = exception.Message };
            Console.Error.WriteLine(JsonSerializer.Serialize(error));
            return 2;
        }
        finally
        {
            TryDelete(working);
            TryDelete(rebuilt);
        }
    }

    private static void ValidatePaths(string source, string manifest, string output)
    {
        if (!File.Exists(source))
            throw new FileNotFoundException("Source ISO was not found.", source);
        if (!File.Exists(manifest))
            throw new FileNotFoundException("Patch manifest was not found.", manifest);
        if (string.Equals(source, output, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Output ISO must not overwrite the source ISO.");
        if (File.Exists(output))
            throw new IOException($"Output already exists: {output}");
    }

    private static void ValidateSource(string source, JsonElement sourceSpec)
    {
        long actualSize = new FileInfo(source).Length;
        if (sourceSpec.TryGetProperty("size", out JsonElement sizeElement) &&
            sizeElement.ValueKind != JsonValueKind.Null &&
            sizeElement.GetInt64() != actualSize)
        {
            throw new InvalidDataException(
                $"Source ISO size mismatch: expected {sizeElement.GetInt64()}, found {actualSize}.");
        }

        string expectedHash = RequiredString(sourceSpec, "sha256").ToLowerInvariant();
        if (expectedHash.Length != 64 || expectedHash.Any(character => !Uri.IsHexDigit(character)))
            throw new InvalidDataException("Manifest source.sha256 must be a full SHA-256 hash.");

        string actualHash = HashFile(source);
        if (!string.Equals(expectedHash, actualHash, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Source ISO SHA-256 mismatch. The exact verified source image is required.");
    }

    private static List<Verification> ApplyOperations(
        string workingIso,
        string manifestPath,
        JsonElement operations)
    {
        string manifestDirectory = Path.GetDirectoryName(manifestPath) ?? Directory.GetCurrentDirectory();
        List<Verification> verifications = new();
        Dictionary<string, List<(long Start, long End)>> byteRanges =
            new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> replacedPaths = new(StringComparer.OrdinalIgnoreCase);

        using UdfEditor editor = new(workingIso);
        int index = 0;
        foreach (JsonElement operation in operations.EnumerateArray())
        {
            index++;
            string id = OptionalString(operation, "id") ?? $"operation-{index}";
            string type = RequiredString(operation, "type");
            string isoPath = NormalizeIsoPath(RequiredString(operation, "path"));
            FileIdentifier file = FindIsoFile(editor, isoPath);

            if (type == "write_bytes")
            {
                if (replacedPaths.Contains(isoPath))
                    throw new InvalidDataException($"{id}: byte writes cannot share a file with replace_file.");

                long offset = operation.GetProperty("offset").GetInt64();
                byte[] expected = ParseHex(RequiredString(operation, "expected_hex"), $"{id}.expected_hex");
                byte[] replacement = ParseHex(RequiredString(operation, "replacement_hex"), $"{id}.replacement_hex");
                if (expected.Length != replacement.Length)
                    throw new InvalidDataException($"{id}: expected and replacement byte lengths differ.");

                long end = checked(offset + expected.Length);
                List<(long Start, long End)> ranges =
                    byteRanges.TryGetValue(isoPath, out var existing) ? existing : byteRanges[isoPath] = new();
                if (ranges.Any(range => offset < range.End && end > range.Start))
                    throw new InvalidDataException($"{id}: byte write overlaps another operation in {isoPath}.");
                ranges.Add((offset, end));

                using Stream stream = editor.GetFileStream(file);
                byte[] actual = ReadRange(stream, offset, expected.Length, id);
                if (!actual.SequenceEqual(expected))
                    throw new InvalidDataException($"{id}: original bytes do not match at {isoPath}+0x{offset:X}.");
                stream.Position = offset;
                stream.Write(replacement);
                stream.Flush();
                verifications.Add(new(id, type, isoPath, offset, replacement, null));
                continue;
            }

            if (type == "replace_file")
            {
                if (replacedPaths.Contains(isoPath) || byteRanges.ContainsKey(isoPath))
                    throw new InvalidDataException($"{id}: replace_file must be the only operation for {isoPath}.");

                string payloadValue = RequiredString(operation, "source_file");
                string payload = Path.IsPathRooted(payloadValue)
                    ? Path.GetFullPath(payloadValue)
                    : Path.GetFullPath(Path.Combine(manifestDirectory, payloadValue));
                if (!File.Exists(payload))
                    throw new FileNotFoundException($"{id}: replacement file was not found.", payload);

                string expectedHash = RequiredString(operation, "expected_sha256");
                using (Stream original = editor.GetFileStream(file))
                {
                    string actualHash = HashStream(original);
                    if (!string.Equals(expectedHash, actualHash, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException($"{id}: original ISO file hash does not match.");
                }

                using (FileStream replacement = File.OpenRead(payload))
                    editor.ReplaceFileStream(file, replacement, true);

                replacedPaths.Add(isoPath);
                verifications.Add(new(id, type, isoPath, 0, null, HashFile(payload)));
                continue;
            }

            throw new InvalidDataException($"{id}: unsupported operation type '{type}'.");
        }

        return verifications;
    }

    private static void VerifyOutput(string outputIso, IEnumerable<Verification> verifications)
    {
        using UdfEditor verifier = new(outputIso);
        foreach (Verification verification in verifications)
        {
            FileIdentifier file = FindIsoFile(verifier, verification.IsoPath);
            using Stream stream = verifier.GetFileStream(file);
            if (verification.Type == "replace_file")
            {
                string actualHash = HashStream(stream);
                if (!string.Equals(actualHash, verification.Sha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException($"Output verification failed for {verification.Id}.");
            }
            else
            {
                byte[] actual = ReadRange(stream, verification.Offset, verification.Bytes!.Length, verification.Id);
                if (!actual.SequenceEqual(verification.Bytes))
                    throw new InvalidDataException($"Output verification failed for {verification.Id}.");
            }
        }
    }

    private static FileIdentifier FindIsoFile(UdfEditor editor, string path)
    {
        string backslash = path.Replace('/', '\\');
        FileIdentifier? file =
            editor.GetFileByName(path) ??
            editor.GetFileByName(backslash) ??
            editor.GetFileByName(Path.GetFileName(path));
        return file ?? throw new FileNotFoundException($"ISO file was not found: {path}");
    }

    private static byte[] ReadRange(Stream stream, long offset, int length, string id)
    {
        if (offset < 0 || offset + length > stream.Length)
            throw new InvalidDataException($"{id}: byte range exceeds the ISO file.");
        stream.Position = offset;
        byte[] data = new byte[length];
        stream.ReadExactly(data);
        return data;
    }

    private static byte[] ParseHex(string value, string field)
    {
        string compact = string.Concat(value.Where(character => !char.IsWhiteSpace(character)));
        if (compact.Length == 0 || compact.Length % 2 != 0)
            throw new InvalidDataException($"{field} must contain complete hexadecimal bytes.");
        try
        {
            return Convert.FromHexString(compact);
        }
        catch (FormatException exception)
        {
            throw new InvalidDataException($"{field} is not valid hexadecimal data.", exception);
        }
    }

    private static string RequiredString(JsonElement element, string property)
    {
        string? value = OptionalString(element, property);
        return string.IsNullOrWhiteSpace(value)
            ? throw new InvalidDataException($"{property} is required.")
            : value;
    }

    private static string? OptionalString(JsonElement element, string property) =>
        element.TryGetProperty(property, out JsonElement value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()?.Trim()
            : null;

    private static string NormalizeIsoPath(string path) =>
        path.Replace('\\', '/').Trim().TrimStart('/');

    private static string HashFile(string path)
    {
        using FileStream stream = File.OpenRead(path);
        return HashStream(stream);
    }

    private static string HashStream(Stream stream)
    {
        long originalPosition = stream.CanSeek ? stream.Position : 0;
        if (stream.CanSeek)
            stream.Position = 0;
        using SHA256 sha = SHA256.Create();
        string result = Convert.ToHexString(sha.ComputeHash(stream)).ToLowerInvariant();
        if (stream.CanSeek)
            stream.Position = originalPosition;
        return result;
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
                File.Delete(path);
        }
        catch
        {
            // A failed cleanup must not hide the patch result or the original error.
        }
    }
}
