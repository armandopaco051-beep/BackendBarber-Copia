from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
import html

from django.http import HttpResponse
from django.utils.text import slugify


def parse_bool(value):
    if value is None or value == '':
        return None
    return str(value).lower() in ['1', 'true', 'si', 'yes']


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def format_value(value):
    if value is None:
        return ''
    return str(value)


def _xml_cell(value, row, column):
    value = html.escape(format_value(value))
    return f'<c r="{column}{row}" t="inlineStr"><is><t>{value}</t></is></c>'


def _column_name(index):
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def build_xlsx(headers, rows):
    sheet_rows = []
    all_rows = [headers] + rows
    for row_index, row in enumerate(all_rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            cells.append(_xml_cell(value, row_index, _column_name(column_index)))
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        '</worksheet>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Reporte" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )

    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types_xml)
        archive.writestr('_rels/.rels', rels_xml)
        archive.writestr('xl/workbook.xml', workbook_xml)
        archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels_xml)
        archive.writestr('xl/worksheets/sheet1.xml', sheet_xml)
    return output.getvalue()


def _pdf_escape(text):
    return format_value(text).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def build_pdf(title, headers, rows):
    lines = [title, '']
    lines.append(' | '.join(headers))
    lines.append('-' * 100)
    for row in rows:
        lines.append(' | '.join(format_value(value) for value in row))

    text_commands = ['BT', '/F1 9 Tf', '40 800 Td']
    first = True
    for line in lines[:55]:
        if not first:
            text_commands.append('0 -14 Td')
        text_commands.append(f'({_pdf_escape(line[:140])}) Tj')
        first = False
    text_commands.append('ET')
    stream = '\n'.join(text_commands)

    objects = [
        '1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj',
        '2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj',
        '3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj',
        '4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj',
        f'5 0 obj << /Length {len(stream.encode("utf-8"))} >> stream\n{stream}\nendstream endobj',
    ]

    pdf = ['%PDF-1.4']
    offsets = [0]
    for obj in objects:
        offsets.append(sum(len(part.encode('utf-8')) + 1 for part in pdf))
        pdf.append(obj)
    xref_offset = sum(len(part.encode('utf-8')) + 1 for part in pdf)
    pdf.append('xref')
    pdf.append(f'0 {len(objects) + 1}')
    pdf.append('0000000000 65535 f ')
    for offset in offsets[1:]:
        pdf.append(f'{offset:010d} 00000 n ')
    pdf.append('trailer << /Size 6 /Root 1 0 R >>')
    pdf.append('startxref')
    pdf.append(str(xref_offset))
    pdf.append('%%EOF')
    return '\n'.join(pdf).encode('utf-8')


def report_response(title, headers, rows, formato, filename):
    formato = (formato or 'pdf').lower()
    safe_filename = slugify(filename) or 'reporte'

    if formato == 'excel':
        content = build_xlsx(headers, rows)
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{safe_filename}.xlsx"'
        return response

    content = build_pdf(title, headers, rows)
    response = HttpResponse(content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{safe_filename}.pdf"'
    return response
