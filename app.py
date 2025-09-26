# app.py
import io
import zipfile
from flask import Flask, render_template, request, send_file, abort
from werkzeug.utils import secure_filename
from renamer import process_files

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024 * 1024  # 128MB

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/', methods=['POST'])
def upload_file():
    files = request.files.getlist('file')
    dry_run = bool(request.form.get('dry_run'))

    if not files:
        abort(400, "Tidak ada file yang diupload.")

    results, outputs = process_files(files, dry_run=dry_run)

    # DRY RUN → tampilkan log tanpa download
    if dry_run:
        return render_template('result.html', logs=results)

    # Tidak ada file sukses → tampilkan log
    if not outputs:
        return render_template('result.html', logs=results)

    # 1 file → kirim langsung PDF
    if len(outputs) == 1:
        name, blob = outputs[0]
        return send_file(
            io.BytesIO(blob),
            as_attachment=True,
            download_name=name,  # <-- jangan secure_filename
            mimetype="application/pdf",
        )

    # >1 file → ZIP in-memory
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, blob in outputs:
            zf.writestr(name, blob)  # <-- jangan secure_filename di sini juga
        # zf.writestr("LOG.txt", "\n".join(results).encode("utf-8"))
    buff.seek(0)

    return send_file(
        buff,
        as_attachment=True,
        download_name="renamed_pdfs.zip",
        mimetype="application/zip",
    )

if __name__ == '__main__':
    app.run(debug=True)
