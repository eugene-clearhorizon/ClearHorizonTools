r"""
Monthly usage email for the transcript cleaner.

Runs as a Cloud Run job, triggered by Cloud Scheduler at 8am Melbourne time on the
1st of each month (see deploy_usage_email.ps1). It reports on the month that just
ended: four headline figures, then a bar chart of each figure by month.

Run it locally from the repo root, with the same .env the app uses:

    .\.venv\Scripts\python.exe -m src.stats.monthly_email --preview output\usage_email
    .\.venv\Scripts\python.exe -m src.stats.monthly_email --month 2026-09

--preview writes the email to a folder as HTML and PNGs without sending anything.
Without it, the email is sent for real.

Sending goes through Mailgun if MAILGUN_API_KEY is set, otherwise SendGrid if
SENDGRID_API_KEY is set. Charts are PNGs attached inline (cid:), because Outlook
renders neither SVG nor data: URIs.

It lives under src/ rather than scripts/ because .gcloudignore keeps scripts/ out
of the container image.
"""

import argparse
import base64
import io
import os
import sys
from datetime import datetime
from email.utils import parseaddr
from html import escape

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import requests
from dotenv import load_dotenv

from .report import by_month, firestore_client, month_range, previous_month, successful_events

TOOL = 'transcript_cleaner'
MAX_MONTHS = 12

# Light only: email clients either show light or auto-invert, and auto-inversion of
# a PNG is out of our hands.
INK = '#0b0b0b'
INK_MUTED = '#52514e'
RULE = '#e4e3df'
BAR = '#2a78d6'          # the month being reported on
BAR_HISTORY = '#a8c7ee'  # earlier months: same hue, recessive

# (key, heading, value from a month's totals, display format)
METRICS = [
    ('runs', 'Runs', lambda m: m['runs'], '{:,.0f}'),
    ('transcripts', 'Transcripts', lambda m: m['files'], '{:,.0f}'),
    ('hours', 'Hours processed', lambda m: m['seconds'] / 3600, '{:,.1f}'),
    ('users', 'Unique users', lambda m: len(m['users']), '{:,.0f}'),
]


def _month_label(key, fmt):
    return datetime.strptime(key, '%Y-%m').strftime(fmt)


def build_report(events, report_month):
    """
    Returns (keys, monthly totals for the charts, all-time totals, first month).

    All-time stops at the end of report_month, so re-sending an old month gives the
    figures as they stood then. Users are unioned, not summed, so someone active in
    several months counts once.
    """
    months, _ = by_month(events)
    first = min(months) if months else report_month
    keys = month_range(first, report_month)[-MAX_MONTHS:] or [report_month]
    empty = {'runs': 0, 'files': 0, 'seconds': 0, 'users': set()}

    all_time = {'runs': 0, 'files': 0, 'seconds': 0, 'users': set()}
    for key, m in months.items():
        if key <= report_month:
            for field in ('runs', 'files', 'seconds'):
                all_time[field] += m[field]
            all_time['users'] |= m['users']

    return keys, [months.get(k, empty) for k in keys], all_time, first


def render_chart(keys, values, fmt):
    """One single-series column chart as PNG bytes. Every column is labelled, so no y-axis."""
    fig, ax = plt.subplots(figsize=(5.6, 2.0), dpi=200)
    colors = [BAR_HISTORY] * (len(keys) - 1) + [BAR]
    bars = ax.bar(range(len(keys)), values, width=0.6, color=colors)

    top = max(values) or 1
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + top * 0.04,
                fmt.format(v), ha='center', va='bottom', fontsize=8, color=INK)

    ax.set_ylim(0, top * 1.25)
    # Always lay out at least six slots, centred, so a young history doesn't draw
    # two slabs across the whole width.
    pad = (max(len(keys), 6) - len(keys)) / 2
    ax.set_xlim(-0.5 - pad, len(keys) - 0.5 + pad)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([_month_label(k, '%b\n%Y') for k in keys], fontsize=7.5, color=INK_MUTED)
    ax.tick_params(axis='x', length=0, pad=4)
    ax.set_yticks([])
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color(RULE)

    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', facecolor='white')
    plt.close(fig)
    return buf.getvalue()


def _change(current, previous, fmt, previous_key):
    if previous is None:
        return 'First month of data'
    diff = current - previous
    if round(diff, 1) == 0:
        return f'Same as {_month_label(previous_key, "%b")}'
    sign = '+' if diff > 0 else '−'
    return f'{sign}{fmt.format(abs(diff))} on {_month_label(previous_key, "%b")}'


def _tile(heading, figure, note):
    return (f'<td width="25%" valign="top" style="padding:12px 8px;border-top:2px solid {BAR};">'
            f'<div style="font-size:12px;color:{INK_MUTED};">{escape(heading)}</div>'
            f'<div style="font-size:28px;font-weight:bold;color:{INK};padding:4px 0;">{figure}</div>'
            f'<div style="font-size:12px;color:{INK_MUTED};">{escape(note)}</div></td>')


def build_email(keys, months, all_time, first):
    """Returns (subject, html, text, {filename: png_bytes})."""
    report_key = keys[-1]
    month_name = _month_label(report_key, '%B %Y')
    since = f'Since {_month_label(first, "%b %Y")}'
    current = months[-1]
    prior = months[-2] if len(months) > 1 else None
    prior_key = keys[-2] if len(keys) > 1 else None

    tiles, total_tiles, charts, images = [], [], [], {}
    text_lines, total_lines = [], []
    for key, heading, value, fmt in METRICS:
        now = value(current)
        change = _change(now, value(prior) if prior else None, fmt, prior_key)
        tiles.append(_tile(heading, fmt.format(now), change))
        total = fmt.format(value(all_time))
        total_tiles.append(_tile(heading, total, since))

        filename = f'{key}.png'
        images[filename] = render_chart(keys, [value(m) for m in months], fmt)
        charts.append(
            f'<tr><td style="padding:20px 0 4px;font-size:15px;font-weight:bold;color:{INK};">'
            f'{escape(heading)} by month</td></tr>'
            f'<tr><td><img src="cid:{filename}" width="560" alt="{escape(heading)} by month" '
            f'style="display:block;width:100%;max-width:560px;height:auto;border:0;"></td></tr>')

        text_lines.append(f'{heading}: {fmt.format(now)} ({change})')
        total_lines.append(f'{heading}: {total}')

    font = "font-family:'Segoe UI',Arial,sans-serif;"
    html = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#ffffff;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="{font}max-width:600px;margin:0 auto;padding:16px;">
<tr><td style="font-size:20px;font-weight:bold;color:{INK};padding-bottom:4px;">Transcript cleaner usage</td></tr>
<tr><td style="font-size:14px;color:{INK_MUTED};padding-bottom:16px;">{escape(month_name)}</td></tr>
<tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="{font}"><tr>{''.join(tiles)}</tr></table></td></tr>
<tr><td style="font-size:14px;color:{INK_MUTED};padding:28px 0 16px;">All time</td></tr>
<tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="{font}"><tr>{''.join(total_tiles)}</tr></table></td></tr>
{''.join(charts)}
<tr><td style="padding-top:24px;font-size:12px;color:{INK_MUTED};line-height:1.5;">
Successful runs only, in Melbourne calendar months. Users are counted by anonymous
hash, so monthly user counts can't be added together &mdash; someone active in two
months appears in both. Sent by the <span style="white-space:nowrap;">usage-email</span> Cloud Run job.
</td></tr>
</table></body></html>"""

    text = '\n'.join([f'Transcript cleaner usage, {month_name}', ''] + text_lines + [
        '', f'All time ({since.lower()})', ''] + total_lines + [
        '', 'Charts are in the HTML version of this email.'])
    return f'Transcript cleaner usage: {month_name}', html, text, images


def _recipients():
    to = [a.strip() for a in os.environ.get('USAGE_EMAIL_TO', '').split(',') if a.strip()]
    sender = os.environ.get('USAGE_EMAIL_FROM', '').strip()
    if not to or not sender:
        raise RuntimeError('USAGE_EMAIL_TO and USAGE_EMAIL_FROM must both be set.')
    return sender, to


def _send_mailgun(sender, to, subject, html, text, images):
    domain = os.environ.get('MAILGUN_DOMAIN')
    if not domain:
        raise RuntimeError('MAILGUN_DOMAIN must be set alongside MAILGUN_API_KEY.')
    # EU-region Mailgun accounts use https://api.eu.mailgun.net instead.
    base = os.environ.get('MAILGUN_API_BASE', 'https://api.mailgun.net').rstrip('/')
    return requests.post(
        f'{base}/v3/{domain}/messages',
        auth=('api', os.environ['MAILGUN_API_KEY']),
        data={'from': sender, 'to': to, 'subject': subject, 'text': text, 'html': html},
        files=[('inline', (name, data, 'image/png')) for name, data in images.items()],
        timeout=60)


def _send_sendgrid(sender, to, subject, html, text, images):
    # SendGrid wants 'Name <address>' split into its parts; Mailgun takes it whole.
    name, address = parseaddr(sender)
    return requests.post(
        'https://api.sendgrid.com/v3/mail/send',
        headers={'Authorization': f'Bearer {os.environ["SENDGRID_API_KEY"]}'},
        json={
            'personalizations': [{'to': [{'email': a} for a in to]}],
            'from': {'email': address, **({'name': name} if name else {})},
            'subject': subject,
            # SendGrid requires text/plain before text/html.
            'content': [{'type': 'text/plain', 'value': text},
                        {'type': 'text/html', 'value': html}],
            'attachments': [{'content': base64.b64encode(data).decode(), 'type': 'image/png',
                             'filename': name, 'disposition': 'inline', 'content_id': name}
                            for name, data in images.items()],
        },
        timeout=60)


def send(subject, html, text, images):
    sender, to = _recipients()
    if os.environ.get('MAILGUN_API_KEY'):
        provider, response = 'Mailgun', _send_mailgun(sender, to, subject, html, text, images)
    elif os.environ.get('SENDGRID_API_KEY'):
        provider, response = 'SendGrid', _send_sendgrid(sender, to, subject, html, text, images)
    else:
        raise RuntimeError('Set MAILGUN_API_KEY or SENDGRID_API_KEY to send the usage email.')
    if not response.ok:
        raise RuntimeError(f'{provider} rejected the email: {response.status_code} {response.text}')
    print(f'Sent "{subject}" to {", ".join(to)} via {provider}.')


def write_preview(folder, html, images):
    os.makedirs(folder, exist_ok=True)
    for name, data in images.items():
        with open(os.path.join(folder, name), 'wb') as f:
            f.write(data)
    with open(os.path.join(folder, 'email.html'), 'w', encoding='utf-8') as f:
        f.write(html.replace('src="cid:', 'src="'))
    print(f'Preview written to {os.path.join(folder, "email.html")}')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0].strip())
    parser.add_argument('--month', help='YYYY-MM to report on (default: last month, Melbourne time)')
    parser.add_argument('--preview', metavar='FOLDER', help='write the email to FOLDER instead of sending it')
    args = parser.parse_args()

    load_dotenv()
    report_month = args.month or previous_month()
    report = build_report(successful_events(firestore_client(), tool=TOOL), report_month)
    subject, html, text, images = build_email(*report)

    if args.preview:
        write_preview(args.preview, html, images)
    else:
        send(subject, html, text, images)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # A non-zero exit is what marks the Cloud Run job execution as failed.
        print(f'Usage email failed: {e}', file=sys.stderr)
        sys.exit(1)
