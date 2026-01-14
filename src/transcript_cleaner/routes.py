from flask import Blueprint, render_template, request, send_from_directory, after_this_request, flash
from werkzeug.utils import secure_filename
import os
import zipfile
from .utils import process_vtt_to_docx

transcript_cleaner_bp = Blueprint('transcript_cleaner', __name__, template_folder='../templates')

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'

@transcript_cleaner_bp.route('/transcript-cleaner', methods=['GET', 'POST'])
def transcript_cleaner():
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    if request.method == 'POST':
        files = request.files.getlist('files[]')
        
        invalid_files = []
        valid_files = []
        for file in files:
            if file.filename == '':
                continue
            if file and file.filename.endswith('.vtt'):
                valid_files.append(file)
            else:
                invalid_files.append(file.filename)

        if invalid_files:
            for filename in invalid_files:
                flash(f'Invalid file type: "{filename}". Only .vtt files are accepted.', 'error')
            return render_template('transcript_cleaner.html')
        
        if not valid_files:
            flash('No files were selected. Please upload one or more .vtt files.', 'warning')
            return render_template('transcript_cleaner.html')

        output_paths = []
        upload_paths = []

        for file in valid_files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            upload_paths.append(filepath)

            output_filename = f"cleaned_{os.path.splitext(filename)[0]}.docx"
            output_filepath = os.path.join(OUTPUT_FOLDER, output_filename)
            output_paths.append(output_filepath)

            process_vtt_to_docx(filepath, output_filepath)

        @after_this_request
        def cleanup(response):
            for path in upload_paths + output_paths:
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"Error cleaning up file: {e}")
            
            if len(output_paths) > 1:
                try:
                    os.remove(os.path.join(OUTPUT_FOLDER, "cleaned_transcripts.zip"))
                except Exception as e:
                    print(f"Error cleaning up zip file: {e}")

            return response

        if len(output_paths) == 1:
            return send_from_directory(os.path.dirname(output_paths[0]), os.path.basename(output_paths[0]), as_attachment=True)
        else:
            zip_filename = "cleaned_transcripts.zip"
            zip_filepath = os.path.join(OUTPUT_FOLDER, zip_filename)
            with zipfile.ZipFile(zip_filepath, 'w') as zipf:
                for path in output_paths:
                    zipf.write(path, os.path.basename(path))
            return send_from_directory(OUTPUT_FOLDER, zip_filename, as_attachment=True)

    return render_template('transcript_cleaner.html')
