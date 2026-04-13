"""
Flask web application for browsing FileMan data in a browser.

Routes:
    GET /                   → redirect to /files
    GET /files              → list all FileMan files (searchable)
    GET /files/<file_num>   → show fields for a file
    GET /files/<file_num>/data  → browse entries (paginated)
    GET /api/files          → JSON: list of all files
    GET /api/files/<file_num>   → JSON: file schema
    GET /api/files/<file_num>/data  → JSON: entries (paginated)
"""

import logging
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

from ..data_dictionary import DataDictionary
from ..file_reader import FileReader

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


def create_app(dd: DataDictionary, reader: FileReader) -> Flask:
    """Create and configure the Flask app.

    Parameters
    ----------
    dd:     Initialized DataDictionary (live YottaDB connection behind it)
    reader: Initialized FileReader
    """
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
    app.config["DD"] = dd
    app.config["READER"] = reader

    @app.route("/")
    def index():  # type: ignore[return]
        return redirect(url_for("files"))

    @app.route("/files")
    def files():  # type: ignore[return]
        query = request.args.get("q", "")
        dd_: DataDictionary = app.config["DD"]
        file_list = dd_.search_files(query) if query else dd_.list_files()
        return render_template("files.html", files=file_list, query=query)

    @app.route("/files/<file_num>")
    def file_detail(file_num: str):  # type: ignore[return]
        dd_: DataDictionary = app.config["DD"]
        file_def = dd_.get_file(float(file_num))
        if file_def is None:
            return f"File {file_num} not found", 404
        fields = sorted(file_def.fields.values(), key=lambda f: f.field_number)
        return render_template("file_detail.html", file_def=file_def, fields=fields)

    @app.route("/files/<file_num>/data")
    def file_data(file_num: str):  # type: ignore[return]
        dd_: DataDictionary = app.config["DD"]
        reader_: FileReader = app.config["READER"]
        file_def = dd_.get_file(float(file_num))
        if file_def is None:
            return f"File {file_num} not found", 404
        limit = int(request.args.get("limit", 50))
        entries = list(reader_.iter_entries(float(file_num), limit=limit))
        fields = sorted(file_def.fields.values(), key=lambda f: f.field_number)
        return render_template(
            "file_data.html",
            file_def=file_def,
            fields=fields,
            entries=entries,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # JSON API
    # ------------------------------------------------------------------

    @app.route("/api/files")
    def api_files():  # type: ignore[return]
        dd_: DataDictionary = app.config["DD"]
        q = request.args.get("q", "")
        file_list = dd_.search_files(q) if q else dd_.list_files()
        return jsonify([{"file_number": n, "label": lbl} for n, lbl in file_list])

    @app.route("/api/files/<file_num>")
    def api_file(file_num: str):  # type: ignore[return]
        dd_: DataDictionary = app.config["DD"]
        file_def = dd_.get_file(float(file_num))
        if file_def is None:
            return jsonify({"error": f"File {file_num} not found"}), 404
        return jsonify(
            {
                "file_number": file_def.file_number,
                "label": file_def.label,
                "global_root": file_def.global_root,
                "field_count": file_def.field_count,
                "fields": [
                    {
                        "field_number": f.field_number,
                        "label": f.label,
                        "datatype_code": f.datatype_code,
                        "datatype_name": f.datatype_name,
                        "title": f.title,
                        "pointer_file": f.pointer_file,
                        "set_values": f.set_values,
                    }
                    for f in sorted(
                        file_def.fields.values(), key=lambda x: x.field_number
                    )
                ],
            }
        )

    @app.route("/api/files/<file_num>/data")
    def api_file_data(file_num: str):  # type: ignore[return]
        reader_: FileReader = app.config["READER"]
        dd_: DataDictionary = app.config["DD"]
        file_def = dd_.get_file(float(file_num))
        if file_def is None:
            return jsonify({"error": f"File {file_num} not found"}), 404
        limit = int(request.args.get("limit", 50))
        entries = list(reader_.iter_entries(float(file_num), limit=limit))
        return jsonify(
            {
                "file_number": float(file_num),
                "label": file_def.label,
                "entries": [
                    {"ien": e.ien, "fields": e.fields, "raw_nodes": e.raw_nodes}
                    for e in entries
                ],
            }
        )

    return app
