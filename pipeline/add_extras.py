from aiida import orm, load_profile
from rich.progress import track

load_profile()

query = orm.QueryBuilder()

query.append(
    orm.Group, filters={'label': 'structure/source'}, tag='group'
).append(
    orm.StructureData, with_group='group', filters={'extras': {'!has_key': 'number_of_sites'}}
).count()

for structure in track(query.all(flat=True)):
    structure.base.extras.set('number_of_sites', len(structure.sites))

print('Finished 🌈')
