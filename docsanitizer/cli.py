"""
Command-line interface for DocSanitizer.

Usage:
    docsanitizer encode document.txt
    docsanitizer decode ai_output.txt --mapping mapping.json
"""

import sys
from pathlib import Path

try:
    import click
except ImportError:
    print("Click not installed. Run: pip install click")
    print("Or use the Python API directly: from docsanitizer import encode, decode")
    sys.exit(1)

from . import __version__
from .encoder import encode, encode_file, get_statistics, generate_legend
from .decoder import decode, decode_file
from .mapper import Mapping


@click.group()
@click.version_option(version=__version__)
def cli():
    """DocSanitizer - Strip sensitive data from documents for AI analysis."""
    pass


@cli.command('encode')
@click.argument('input_file', type=click.Path(exists=True))
@click.option('-o', '--output', type=click.Path(), help='Output file for sanitized text')
@click.option('-m', '--mapping', type=click.Path(), help='Output file for mapping JSON')
@click.option('-l', '--language', default='nl',
              help='Language: nl, en, de, fr, it, es (default: nl)')
@click.option('-s', '--strategy', type=click.Choice(['replace', 'redact', 'mask', 'hash']),
              default='replace', help='Anonymization strategy (default: replace)')
@click.option('-b', '--backend', type=click.Choice(['hybrid', 'patterns']),
              default='hybrid', help='Detection backend (default: hybrid)')
@click.option('--dry-run', is_flag=True, help='Show what would be replaced without writing')
@click.option('--stats', is_flag=True, help='Show statistics after encoding')
@click.option('--legend/--no-legend', default=True, help='Add legend header for AI context (default: on)')
def encode_cmd(input_file, output, mapping, language, strategy, backend, dry_run, stats, legend):
    """
    Sanitize a document by replacing PII with placeholders.

    Detects and replaces: names, locations, emails, phones, IBANs, BSN, dates.
    Supports 6 languages: Dutch, English, German, French, Italian, Spanish.

    Examples:

        docsanitizer encode document.txt

        docsanitizer encode document.txt -l en

        docsanitizer encode document.txt -o sanitized.txt -m mapping.json

        docsanitizer encode document.txt --strategy mask

        docsanitizer encode document.txt --dry-run
    """
    input_path = Path(input_file)

    # Default output paths
    if not output:
        output = input_path.stem + '_sanitized' + input_path.suffix
    if not mapping:
        mapping = input_path.stem + '_mapping.json'

    click.echo(f"Encoding: {input_file}")
    click.echo(f"Backend: {backend}, Strategy: {strategy}, Language: {language}")

    # Read and encode
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()

    sanitized, mapping_obj = encode(text, backend=backend, strategy=strategy, language=language)

    if dry_run:
        click.echo("\n--- DRY RUN - Detected sensitive values ---\n")
        for placeholder, entry in mapping_obj.entries.items():
            click.echo(f"  {placeholder}: {entry.canonical}")
        click.echo(f"\nTotal: {len(mapping_obj.entries)} unique values")
        click.echo("\nNo files written (dry run)")
        return

    # Add legend header if requested (default: on)
    if legend:
        legend_text = generate_legend(mapping_obj)
        sanitized = legend_text + sanitized

    # Write outputs
    with open(output, 'w', encoding='utf-8') as f:
        f.write(sanitized)

    mapping_obj.save(mapping)

    click.echo(f"Sanitized: {output}")
    click.echo(f"Mapping:   {mapping}")
    if legend:
        click.echo("Legend:    Included (helps AI understand placeholders)")

    if stats:
        click.echo("\n--- Statistics ---")
        stat_dict = get_statistics(mapping_obj)
        click.echo(f"Total unique values: {stat_dict['total_unique_values']}")
        click.echo(f"Total occurrences:   {stat_dict['total_occurrences']}")
        for cat, cat_stats in stat_dict['by_category'].items():
            click.echo(f"\n{cat}:")
            click.echo(f"  Unique: {cat_stats['unique']}")
            click.echo(f"  Occurrences: {cat_stats['occurrences']}")
            for example in cat_stats['examples']:
                click.echo(f"    {example}")


@cli.command('decode')
@click.argument('input_file', type=click.Path(exists=True))
@click.option('-m', '--mapping', type=click.Path(exists=True), required=True,
              help='Mapping JSON file from encoding')
@click.option('-o', '--output', type=click.Path(), help='Output file for decoded text')
def decode_cmd(input_file, mapping, output):
    """
    Decode placeholders back to original values.

    Use this on AI output to restore real names/values.

    Examples:

        docsanitizer decode ai_output.txt -m mapping.json

        docsanitizer decode ai_output.txt -m mapping.json -o final_report.txt
    """
    input_path = Path(input_file)

    # Default output path
    if not output:
        output = input_path.stem + '_decoded' + input_path.suffix

    click.echo(f"Decoding: {input_file}")
    click.echo(f"Using mapping: {mapping}")

    decoded = decode_file(input_path, mapping, output)

    click.echo(f"Output: {output}")


@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
def analyze(input_file):
    """
    Analyze a document for sensitive data without encoding.

    Shows what would be detected and replaced.
    """
    from .detectors import detect_all

    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()

    matches = detect_all(text)

    click.echo(f"\nAnalyzing: {input_file}")
    click.echo(f"File size: {len(text):,} characters\n")

    # Group by category
    by_category = {}
    for match in matches:
        if match.category not in by_category:
            by_category[match.category] = []
        by_category[match.category].append(match)

    for category, cat_matches in sorted(by_category.items()):
        click.echo(f"\n{category} ({len(cat_matches)} found):")
        # Show first 5 examples
        for match in cat_matches[:5]:
            click.echo(f"  - {match.text}")
        if len(cat_matches) > 5:
            click.echo(f"  ... and {len(cat_matches) - 5} more")

    click.echo(f"\n\nTotal: {len(matches)} sensitive values detected")


@cli.command()
@click.argument('mapping_file', type=click.Path(exists=True))
def show_mapping(mapping_file):
    """Show contents of a mapping file."""
    mapping = Mapping.load(mapping_file)

    click.echo(f"\nMapping: {mapping_file}")
    click.echo(f"Version: {mapping.version}")
    click.echo(f"Created: {mapping.created}")
    click.echo(f"\nEntries ({len(mapping.entries)}):\n")

    for placeholder, entry in sorted(mapping.entries.items()):
        click.echo(f"  {placeholder}:")
        click.echo(f"    Canonical: {entry.canonical}")
        if len(entry.variations) > 1:
            click.echo(f"    Variations: {entry.variations}")
        click.echo(f"    Occurrences: {entry.occurrences}")


@cli.command('convert')
@click.argument('pdf_file', type=click.Path(exists=True))
@click.option('-o', '--output-dir', type=click.Path(), help='Output directory for text files')
@click.option('-b', '--backend', type=click.Choice(['auto', 'marker', 'tesseract']),
              default='auto', help='OCR backend: auto, marker (best), tesseract (fallback)')
@click.option('--split/--no-split', default=False, help='Split into multiple files')
@click.option('--max-pages', default=500, help='Max pages per file when splitting (default: 500)')
@click.option('--info', is_flag=True, help='Just show PDF info, do not convert')
def convert_cmd(pdf_file, output_dir, backend, split, max_pages, info):
    """
    Convert PDF to text with OCR support.

    Handles both native PDFs and scanned documents.
    Uses marker-pdf (best accuracy) or pytesseract (fallback).

    Examples:

        docsanitizer convert document.pdf

        docsanitizer convert document.pdf -o ./output/

        docsanitizer convert document.pdf --backend marker

        docsanitizer convert large.pdf --split --max-pages 500

        docsanitizer convert document.pdf --info
    """
    from .converter import convert_pdf, get_pdf_info, get_available_converters

    pdf_path = Path(pdf_file)

    # Show available converters
    available = get_available_converters()
    click.echo(f"\nAvailable converters:")
    click.echo(f"  marker-pdf: {'yes' if available['marker'] else 'no (pip install marker-pdf)'}")
    click.echo(f"  tesseract:  {'yes' if available['tesseract'] else 'no (pip install pymupdf pytesseract pdf2image)'}")

    # Just show info
    if info:
        pdf_info = get_pdf_info(pdf_file)
        click.echo(f"\nPDF Info:")
        click.echo(f"  File: {pdf_info['path']}")
        click.echo(f"  Size: {pdf_info['size_mb']:.1f} MB")
        if 'pages' in pdf_info:
            click.echo(f"  Pages: {pdf_info['pages']}")
        if pdf_info.get('title'):
            click.echo(f"  Title: {pdf_info['title']}")
        return

    # Default output directory
    if not output_dir:
        output_dir = pdf_path.parent

    click.echo(f"\nConverting: {pdf_file}")
    click.echo(f"Backend: {backend}")
    click.echo(f"Output: {output_dir}")

    try:
        text, metadata = convert_pdf(
            pdf_file,
            output_dir=output_dir,
            backend=backend,
            split_pages=split,
            max_pages_per_file=max_pages,
        )

        click.echo(f"\nDone!")
        click.echo(f"Converter used: {metadata.get('converter', 'unknown')}")
        if 'total_pages' in metadata:
            click.echo(f"Pages: {metadata['total_pages']} ({metadata.get('native_pages', 0)} native, {metadata.get('ocr_pages', 0)} OCR)")
        if 'output_file' in metadata:
            click.echo(f"Output: {metadata['output_file']}")
        click.echo(f"Text length: {len(text):,} characters")

        click.echo(f"\nNext step: docsanitizer encode {metadata.get('output_file', pdf_path.stem + '.txt')}")

    except ImportError as e:
        click.echo(f"\nError: {e}")
        click.echo("\nInstall a converter:")
        click.echo("  pip install marker-pdf          (recommended, best accuracy)")
        click.echo("  pip install pymupdf pytesseract pdf2image  (fallback)")
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nError: {e}")
        sys.exit(1)


def main():
    """Entry point."""
    cli()


if __name__ == '__main__':
    main()
