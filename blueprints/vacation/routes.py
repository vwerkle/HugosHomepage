from flask import Blueprint, render_template, request, session, jsonify, current_app
import os, json, uuid, random
from werkzeug.utils import secure_filename

vacation_bp = Blueprint('vacation', __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, '..', '..', 'data', 'vacation', 'trips.json')
STATIC_DIR = os.path.join(BASE_DIR, '..', '..', 'static', 'vacation')
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

_COUNTRY_CODES = {
    'Afghanistan':'AF','Albania':'AL','Algeria':'DZ','Argentina':'AR','Armenia':'AM',
    'Australia':'AU','Austria':'AT','Azerbaijan':'AZ','Bahamas':'BS','Bahrain':'BH',
    'Bangladesh':'BD','Barbados':'BB','Belgium':'BE','Belize':'BZ','Bolivia':'BO',
    'Bosnia':'BA','Botswana':'BW','Brazil':'BR','Bulgaria':'BG','Cambodia':'KH',
    'Cameroon':'CM','Canada':'CA','Chile':'CL','China':'CN','Colombia':'CO',
    'Costa Rica':'CR','Croatia':'HR','Cuba':'CU','Curacao':'CW','Cyprus':'CY',
    'Czech Republic':'CZ','Czechia':'CZ','Denmark':'DK','Dominican Republic':'DO',
    'Ecuador':'EC','Egypt':'EG','El Salvador':'SV','England':'GB','Estonia':'EE',
    'Ethiopia':'ET','Finland':'FI','France':'FR','Georgia':'GE','Germany':'DE',
    'Ghana':'GH','Greece':'GR','Grenada':'GD','Guatemala':'GT','Haiti':'HT',
    'Honduras':'HN','Hong Kong':'HK','Hungary':'HU','Iceland':'IS','India':'IN',
    'Indonesia':'ID','Iran':'IR','Iraq':'IQ','Ireland':'IE','Israel':'IL',
    'Italy':'IT','Jamaica':'JM','Japan':'JP','Jordan':'JO','Kazakhstan':'KZ',
    'Kenya':'KE','Kuwait':'KW','Laos':'LA','Latvia':'LV','Lebanon':'LB',
    'Lithuania':'LT','Luxembourg':'LU','Madagascar':'MG','Malaysia':'MY',
    'Maldives':'MV','Malta':'MT','Mexico':'MX','Montenegro':'ME','Morocco':'MA',
    'Mozambique':'MZ','Myanmar':'MM','Namibia':'NA','Nepal':'NP','Netherlands':'NL',
    'New Zealand':'NZ','Nicaragua':'NI','Nigeria':'NG','Norway':'NO','Oman':'OM',
    'Pakistan':'PK','Panama':'PA','Peru':'PE','Philippines':'PH','Poland':'PL',
    'Portugal':'PT','Puerto Rico':'PR','Qatar':'QA','Romania':'RO','Rwanda':'RW',
    'Saudi Arabia':'SA','Scotland':'GB','Senegal':'SN','Serbia':'RS',
    'Singapore':'SG','Slovakia':'SK','Slovenia':'SI','South Africa':'ZA',
    'South Korea':'KR','Korea':'KR','Spain':'ES','Sri Lanka':'LK','Sweden':'SE',
    'Switzerland':'CH','Taiwan':'TW','Tanzania':'TZ','Thailand':'TH',
    'Trinidad':'TT','Trinidad and Tobago':'TT','Tunisia':'TN','Turkey':'TR',
    'UAE':'AE','Uganda':'UG','UK':'GB','Ukraine':'UA','United Arab Emirates':'AE',
    'United Kingdom':'GB','United States':'US','USA':'US','Uruguay':'UY',
    'Uzbekistan':'UZ','Vietnam':'VN','Zambia':'ZM','Zimbabwe':'ZW',
    'Cayman Islands':'KY','Aruba':'AW','St Lucia':'LC','Saint Lucia':'LC',
    'Antigua':'AG','Turks and Caicos':'TC','Bermuda':'BM',
}

def _flag(country):
    code = _COUNTRY_CODES.get(country or '', '')
    if len(code) == 2:
        return chr(0x1F1E6 + ord(code[0]) - 65) + chr(0x1F1E6 + ord(code[1]) - 65)
    return ''

def load_trips():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE) as f:
        trips = json.load(f)
    for trip in trips:
        trip['flag'] = _flag(trip.get('country', ''))
        for key in ('things_to_do', 'restaurants', 'hotels'):
            trip[key] = sorted(trip.get(key, []), key=lambda x: x.get('stars', 0), reverse=True)
    return trips

def save_trips(trips):
    with open(DATA_FILE, 'w') as f:
        json.dump(trips, f, indent=2)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def is_admin():
    return session.get('user') == 'hugo'


def _prepare(template):
    trips = load_trips()
    random.shuffle(trips)
    regions = sorted({t.get('region', '') for t in trips if t.get('region')})
    return render_template(template, trips=trips, regions=regions, is_admin=is_admin())

@vacation_bp.route('/')
def index():
    return _prepare('vacation/index.html')

@vacation_bp.route('/2')
def index2():
    return _prepare('vacation/index2.html')

@vacation_bp.route('/3')
def index3():
    return _prepare('vacation/index3.html')


@vacation_bp.route('/admin/add', methods=['POST'])
def add_trip():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    trip_id = data.get('title', 'trip').lower().replace(' ', '-') + '-' + str(uuid.uuid4())[:4]
    trip = {
        'id': trip_id,
        'title': data.get('title', ''),
        'country': data.get('country', ''),
        'region': data.get('region', ''),
        'dates': data.get('dates', ''),
        'description': data.get('description', ''),
        'main_image': '',
        'images': [],
        'lat': data.get('lat', ''),
        'lng': data.get('lng', ''),
        'things_to_do': [],
        'restaurants': [],
        'hotels': [],
        'notes': data.get('notes', ''),
    }
    trips = load_trips()
    trips.append(trip)
    save_trips(trips)
    os.makedirs(os.path.join(STATIC_DIR, trip_id), exist_ok=True)
    return jsonify({'id': trip_id})


@vacation_bp.route('/admin/edit/<trip_id>', methods=['POST'])
def edit_trip(trip_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    trips = load_trips()
    for trip in trips:
        if trip['id'] == trip_id:
            for key in ('title', 'country', 'region', 'dates', 'description', 'lat', 'lng', 'notes',
                        'things_to_do', 'restaurants', 'hotels', 'main_image', 'images'):
                if key in data:
                    trip[key] = data[key]
            break
    save_trips(trips)
    return jsonify({'ok': True})


@vacation_bp.route('/admin/delete/<trip_id>', methods=['POST'])
def delete_trip(trip_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    trips = load_trips()
    trips = [t for t in trips if t['id'] != trip_id]
    save_trips(trips)
    return jsonify({'ok': True})


@vacation_bp.route('/admin/upload/<trip_id>', methods=['POST'])
def upload_image(trip_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    file = request.files.get('image')
    if not file or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file'}), 400
    dest_dir = os.path.join(STATIC_DIR, trip_id)
    os.makedirs(dest_dir, exist_ok=True)
    filename = secure_filename(file.filename)
    file.save(os.path.join(dest_dir, filename))

    # If flagged as main, update trips.json
    if request.form.get('is_main') == '1':
        trips = load_trips()
        for trip in trips:
            if trip['id'] == trip_id:
                trip['main_image'] = filename
                if filename not in trip['images']:
                    trip['images'].insert(0, filename)
                break
        save_trips(trips)
    else:
        trips = load_trips()
        for trip in trips:
            if trip['id'] == trip_id:
                if filename not in trip['images']:
                    trip['images'].append(filename)
                break
        save_trips(trips)

    return jsonify({'filename': filename})
