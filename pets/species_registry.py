# pets/species_registry.py

PET_SPECIES_REGISTRY = {
    'fox': {
        'id': 'fox',
        'family_name': 'Zorro Kitsune Astral',
        'element': 'Luz & Fortuna',
        'stages': [
            {'stage': 1, 'name': 'Kitling', 'min_lvl': 1, 'title': 'Cachorro Solar ✨', 'sprite': 'Kitling.png', 'buff_desc': 'Bono diario cada 22h y expedición rápida (+10%)'},
            {'stage': 2, 'name': 'Kitsuray', 'min_lvl': 10, 'title': 'Zorro de Tres Colas 🦊', 'sprite': 'Kitsuray.png', 'buff_desc': 'Bono diario cada 20h y expedición rápida (+20%)'},
            {'stage': 3, 'name': 'Kitsunami Imperial', 'min_lvl': 25, 'title': 'Soberano de Nueve Colas ⚜️', 'sprite': 'Kitsunami.png', 'buff_desc': 'Bono diario cada 18h y expedición rápida (+35%)'},
        ]
    },
    'panther': {
        'id': 'panther',
        'family_name': 'Pantera de Ébano',
        'element': 'Sombra & Fortuna',
        'stages': [
            {'stage': 1, 'name': 'Nocx', 'min_lvl': 1, 'title': 'Cría Umbría 🐾', 'sprite': 'Nocx.png', 'buff_desc': '+10% de Oro extra en victorias de Casino'},
            {'stage': 2, 'name': 'Umbrather', 'min_lvl': 10, 'title': 'Pantera Nocturna 🐆', 'sprite': 'Umbrather.png', 'buff_desc': '+18% de Oro extra en victorias de Casino'},
            {'stage': 3, 'name': 'Nyxador Soberano', 'min_lvl': 25, 'title': 'Gran Señor del Vacío 👑', 'sprite': 'Nyxador Soberano.png', 'buff_desc': '+28% de Oro extra en victorias de Casino'},
        ]
    },
    'viper': {
        'id': 'viper',
        'family_name': 'Víbora Esmeralda',
        'element': 'Veneno & Seducción',
        'stages': [
            {'stage': 1, 'name': 'Serpet', 'min_lvl': 1, 'title': 'Sierpe de Jade 🐍', 'sprite': 'Serpet.png', 'buff_desc': '15% de Descuento en fotos de KingdomFans'},
            {'stage': 2, 'name': 'Viperis', 'min_lvl': 10, 'title': 'Cobra Regia 👑', 'sprite': 'Viperis.png', 'buff_desc': '22% de Descuento en fotos de KingdomFans'},
            {'stage': 3, 'name': 'Ouroboria Reina', 'min_lvl': 25, 'title': 'Diosa Alada Emplumada ⚜️', 'sprite': 'Ouroboria Reina.png', 'buff_desc': '30% de Descuento en fotos de KingdomFans'},
        ]
    },
    'raven': {
        'id': 'raven',
        'family_name': 'Cuervo Abisal',
        'element': 'Medianoche & Destino',
        'stages': [
            {'stage': 1, 'name': 'Corvyn', 'min_lvl': 1, 'title': 'Polluelo Arcano 🪶', 'sprite': 'Corvyn.png', 'buff_desc': '+20% de probabilidad de Jackpots en Slots'},
            {'stage': 2, 'name': 'Ravencore', 'min_lvl': 10, 'title': 'Cuervo de Medianoche 🦅', 'sprite': 'Ravencore.png', 'buff_desc': '+35% de probabilidad de Jackpots en Slots'},
            {'stage': 3, 'name': 'Kranor Arcano', 'min_lvl': 25, 'title': 'Fénix Estelar Cósmico 👑', 'sprite': 'Kranor Arcano.png', 'buff_desc': '+55% de probabilidad de Jackpots en Slots'},
        ]
    },
    'wolf': {
        'id': 'wolf',
        'family_name': 'Lobo Espectral',
        'element': 'Escarcha & Escudo',
        'stages': [
            {'stage': 1, 'name': 'Lupen', 'min_lvl': 1, 'title': 'Lobicito Ártico 🐺', 'sprite': 'Lupen.png', 'buff_desc': '10% de Protección contra derrotas en Blackjack'},
            {'stage': 2, 'name': 'Fenris de Plata', 'min_lvl': 10, 'title': 'Lobo de Runas Lunares 🌙', 'sprite': 'Fenris.png', 'buff_desc': '18% de Protección contra derrotas en Blackjack'},
            {'stage': 3, 'name': 'Skollgard Titán', 'min_lvl': 25, 'title': 'Monarca de Hielo Imperial 👑', 'sprite': 'Skollgard.png', 'buff_desc': '25% de Protección contra derrotas en Blackjack'},
        ]
    },
    'dragon': {
        'id': 'dragon',
        'family_name': 'Dragón Carmesí',
        'element': 'Fuego & Rubí',
        'stages': [
            {'stage': 1, 'name': 'Drakito', 'min_lvl': 1, 'title': 'Dragoncito de Rubí 🐉', 'sprite': 'Drakito.png', 'buff_desc': '+0.10x Multiplicador en Minas del Reino'},
            {'stage': 2, 'name': 'Pyralis Noble', 'min_lvl': 10, 'title': 'Dragón Oriental Sagrado 🔥', 'sprite': 'Pyralis.png', 'buff_desc': '+0.25x Multiplicador en Minas del Reino'},
            {'stage': 3, 'name': 'Aethelgard Rey', 'min_lvl': 25, 'title': 'Emperador del Magma 👑', 'sprite': 'Aethelgard.png', 'buff_desc': '+0.50x Multiplicador en Minas del Reino'},
        ]
    },
    'owl': {
        'id': 'owl',
        'family_name': 'Búho Cronos',
        'element': 'Tiempo & Sabiduría',
        'stages': [
            {'stage': 1, 'name': 'Owlet', 'min_lvl': 1, 'title': 'Lechucita con Monóculo 🦉', 'sprite': 'Owlet.png', 'buff_desc': '+15% EXP nobiliaria en todas las acciones'},
            {'stage': 2, 'name': 'Stryx Nocturno', 'min_lvl': 10, 'title': 'Búho del Reloj de Arena ⏳', 'sprite': 'Stryx.png', 'buff_desc': '+30% EXP nobiliaria en todas las acciones'},
            {'stage': 3, 'name': 'Chronix Arconte', 'min_lvl': 25, 'title': 'Arconte del Destino Estelar 👑', 'sprite': 'Chronix.png', 'buff_desc': '+50% EXP nobiliaria en todas las acciones'},
        ]
    },
    'deer': {
        'id': 'deer',
        'family_name': 'Ciervo de Jade',
        'element': 'Naturaleza & Rocío',
        'stages': [
            {'stage': 1, 'name': 'Fawny', 'min_lvl': 1, 'title': 'Cervatillo de Cristal 🦌', 'sprite': 'Fawny.png', 'buff_desc': '15% de probabilidad de botín doble en expedición'},
            {'stage': 2, 'name': 'Silvandor', 'min_lvl': 10, 'title': 'Venado de Cuernos Dorados 🌿', 'sprite': 'Silvandor.png', 'buff_desc': '25% de probabilidad de botín doble en expedición'},
            {'stage': 3, 'name': 'Cernunnos Divino', 'min_lvl': 25, 'title': 'Deidad del Bosque Eterno 👑', 'sprite': 'Cernunnos.png', 'buff_desc': '40% de probabilidad de botín doble en expedición'},
        ]
    },
    'scorpion': {
        'id': 'scorpion',
        'family_name': 'Escorpión Dorado',
        'element': 'Arena & Oro',
        'stages': [
            {'stage': 1, 'name': 'Scorpi', 'min_lvl': 1, 'title': 'Arácnido de Ámbar 🦂', 'sprite': 'Scorpi.png', 'buff_desc': '5% Cashback de oro en compras y brindis'},
            {'stage': 2, 'name': 'Venomarch', 'min_lvl': 10, 'title': 'Escorpión Acorazado ⚡', 'sprite': 'Venomarch.png', 'buff_desc': '10% Cashback de oro en compras y brindis'},
            {'stage': 3, 'name': 'Azrael de las Dunas', 'min_lvl': 25, 'title': 'Faraón de las Arenas 👑', 'sprite': 'Azrael.png', 'buff_desc': '15% Cashback de oro en compras y brindis'},
        ]
    },
    'rabbit': {
        'id': 'rabbit',
        'family_name': 'Conejo Lunar',
        'element': 'Seda & Misticismo',
        'stages': [
            {'stage': 1, 'name': 'Bunbún', 'min_lvl': 1, 'title': 'Conejito de Seda 🐇', 'sprite': 'Bunbún.png', 'buff_desc': '+5% probabilidad de Photocards Legendarias'},
            {'stage': 2, 'name': 'Lunaris', 'min_lvl': 10, 'title': 'Liebre de Perlas Lunares ✨', 'sprite': 'Lunaris.png', 'buff_desc': '+12% probabilidad de Photocards Legendarias'},
            {'stage': 3, 'name': 'Tsukuyomi Reina', 'min_lvl': 25, 'title': 'Diosa Lunar de la Seda 👑', 'sprite': 'Tsukuyomi.png', 'buff_desc': '+20% probabilidad de Photocards Legendarias'},
        ]
    }
}

def get_species_data(species_id):
    return PET_SPECIES_REGISTRY.get(str(species_id).lower(), PET_SPECIES_REGISTRY['fox'])

def get_evolution_stage(species_id, level):
    data = get_species_data(species_id)
    stages = data['stages']
    current = stages[0]
    for s in stages:
        if level >= s['min_lvl']:
            current = s
    return current