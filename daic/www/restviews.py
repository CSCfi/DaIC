from flask import (abort, jsonify, request, send_from_directory)
from werkzeug.utils import secure_filename
from datetime import datetime

import json
import uuid
import os
import shutil

from daic.models import Container, File, UploadToken
from daic.www import app, with_db_session


@app.route('/v1')
def api_root_v1():
    return '''<ul>
    <li>/v1/containers [GET]</li>
    <li>/v1/containers/(container_id) [GET]</li>
    <li>/v1/containers/download/(container_id) [GET]</li>
    <li>/v1/containers/upload [POST]</li>
    <li>/v1/containers/token [GET, POST]</li>'''


@app.route('/v1/containers', methods=['GET'])
@with_db_session
def api_list_containers(session):
    return json.dumps([{'id': x.uuid, 'name': x.name}
                       for x in session.query(Container).all()],
                      indent=4)


@with_db_session
def get_container(session, container_id):
    return session.query(Container).filter_by(uuid=container_id).first()


@with_db_session
def get_file(session, container_id, file_id):
    container = get_container(container_id)
    if not container:
        abort(404)
    return session.query(File).filter_by(container = container.id,
                                         uuid = file_id).first()


@with_db_session
def get_container_token(session, container_token):
    return session.query(UploadToken).filter_by(uuid=container_token).first()


@app.route('/v1/containers/<container_id>', methods=['GET'])
@with_db_session
def api_get_container(session, container_id):
    container = get_container(container_id)
    if container:
        files = [{'uuid': x.uuid, 'name': x.name} for x
                 in session.query(File).filter(File.container == container.id)]
        return jsonify({'id': container.uuid,
                        'name': container.name,
                        'files': files})
    else:
        return abort(404)


@app.route('/v1/containers/<container_id>/files/<file_id>', methods=['GET'])
@with_db_session
def api_get_file_from_container(session, container_id, file_id):
    resource = get_file(container_id, file_id)
    if not resource:
        abort(404)
    return jsonify(resource.to_dict())


@app.route('/v1/containers/token', methods=['GET', 'POST'])
@with_db_session
def api_create_upload_token(session):
    token = UploadToken()
    token.uuid = uuid.uuid1().get_hex()
    session.add(token)
    session.commit()
    return jsonify({'id': token.uuid})


@app.route('/v1/containers', methods=['POST'])
@with_db_session
def api_create_container(session):
#    request_token = request.headers.get('x-auth-token')
#    token = get_container_token(request_token)
#    if not token:
#        abort(403)

    if request.method == 'POST':
        params = dict(request.form.items())
        if 'name' in params:
            container = Container()
            container.name = params['name']
            container.uuid = uuid.uuid1().get_hex()
            container.create_ts = datetime.utcnow()
            try:
                os.mkdir(os.path.join(app.config['UPLOAD_FOLDER'],
                                      container.uuid))
            except IOError:
                abort(400)
            session.add(container)
            session.commit()
            return jsonify({'uuid': container.uuid})
        else:
            abort(400)


@app.route('/v1/containers/<container_id>/files', methods=['POST'])
@with_db_session
def api_create_file(session, container_id):
#    request_token = request.headers.get('x-auth-token')
#    token = get_container_token(request_token)
#    if not token:
#        abort(403)
    if request.method == 'POST':
        container = get_container(container_id)
        if not container:
            abort(404)
        upload = request.files['file']
        if upload:
            filename = secure_filename(upload.filename)
            upload.save(os.path.join(app.config['UPLOAD_FOLDER'],
                                     container_id, filename))
            file_uuid = uuid.uuid1().get_hex()
            file = File()
            file.name = filename
            file.uuid = file_uuid
            file.container = container.id
            file.meta = ""
            session.add(file)
#            session.delete(token)
            session.commit()
        return jsonify({'id': file_uuid})


@app.route('/v1/containers/<container_id>', methods=['DELETE'])
@with_db_session
def api_delete_container(session, container_id):
    container = get_container(container_id)
    if not container:
        abort(404)
    try:
        shutil.rmtree(os.path.join(app.config['UPLOAD_FOLDER'],
                                   container.uuid))
    except:
        pass
    for resource in session.query(File).filter(File.container == container.id):
        session.delete(resource)
    session.commit()
    session.delete(container)
    session.commit()
    return jsonify({})


@app.route('/v1/containers/<container_id>/files/<file_id>', methods=['DELETE'])
@with_db_session
def api_delete_file(session, container_id, file_id):
#    request_token = request.headers.get('x-auth-token')
#    token = get_container_token(request_token)
#    if not token:
#        abort(403)

    container = get_container(container_id)
    resource = get_file(container_id, file_id)
    if not resource or not container:
        abort(404)
    if request.method == 'DELETE':
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'],
                                   container.uuid,
                                   resource.name))
        except:
            pass

        session.delete(resource)
#        session.delete(token)
        session.commit()
        app.config['zmqsock'].send(json.dumps({'cmd': 'ui:delete-file',
                                               'file_id': file_id,
                                               'container_id': container_id}))
    return jsonify({})


@app.route('/v1/containers/<container_id>/files/<file_id>/download')
@with_db_session
def download_container(session, container_id, file_id):
    resource = get_file(container_id, file_id)
    if resource:
        return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'],
                                                container_id), resource.name)
    else:
        abort(404)
