import noobcash
from flask import Blueprint
from flask import request

bp = Blueprint('id', __name__, url_prefix='/id')
    
@bp.route('/post', methods=["POST"])
def post():    
    noobcash.current_node.id = request.form['node_id']
    
    return '', 200

@bp.route('/get', methods=["GET"])
def get():    
    return f'{noobcash.current_node.id}', 200