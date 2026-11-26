"""Compact provider grammar with lossless conversion to the existing native schema."""
import copy
from analyze_photo import validate_analysis

FORMAT='compiled-flat-v1'
DISTANCES={
    'closest_visible':'closest_object',
    'closest_subject':'closest_subject',
    'farthest':'farthest_object',
}


def response_schema(native):
    properties=copy.deepcopy(native['anyOf'][0]['properties'])
    features=properties.pop('features')['properties']
    properties['features']={'type':'array','items':{'type':'string','enum':sorted(features)},
        'description':'Only features that are true in this photo. No duplicates; absent flags mean false.'}
    signs=properties.pop('signs_or_writing')['properties']
    properties['signs_present']=signs['present']
    properties['signs_description']=signs['description']
    for prefix,key in DISTANCES.items():
        distance=properties.pop(key)['properties']
        properties[prefix+'_m']=distance['distance_meters']
        properties[prefix+'_description']=distance['description']
    properties={'photo_id':{'type':'string'},**properties}
    label={'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    skipped={'type':'object','properties':{'photo_id':{'type':'string'},'reason':{'type':'string'}},
        'required':['photo_id','reason'],'additionalProperties':False}
    return {'type':'object','properties':{
        'labels':{'type':'array','items':label},'skipped':{'type':'array','items':skipped}},
        'required':['labels','skipped'],'additionalProperties':False}


def instructions():
    return ('\nReturn labels and skipped arrays. Each target UUID must occur exactly once across them. '
        'A normal label is a flat object; do not wrap it in an analysis object. '
        'features lists ONLY true feature names; an empty list means no flags, not unknown. '
        'closest_visible_m describes the literal closest object; closest_subject_m is the closest consequential subject; '
        'farthest_m describes the farthest object. Distances are meters and stay null for sky-only photos. '
        'Keep their descriptions in the corresponding *_description fields. '
        'signs_present/signs_description describe signs_or_writing. '
        'All other rubric meanings are unchanged. Empty descriptions are allowed when nothing applies. '
        'Use skipped only for blank, corrupt, or completely blocked images. '
        'Do not add redundant distance categories, visibility labels or building-height categories; code derives them.')


def native_entries(payload,native,schema):
    if not isinstance(payload,dict) or set(payload)!={'labels','skipped'} or not all(isinstance(payload[k],list) for k in ('labels','skipped')):
        raise ValueError('Expected labels and skipped arrays')
    allowed=native['anyOf'][0]['properties']['features']['properties']
    entries=[]
    for group in ('labels','skipped'):
        for label in payload[group]:
            if not isinstance(label,dict) or not isinstance(label.get('photo_id'),str):
                raise ValueError('Missing photo identity')
            pid=label['photo_id']
            try:
                errors=validate_analysis(label,schema['properties'][group]['items'])
                if errors:raise ValueError('; '.join(errors))
                if group=='skipped':
                    raw={'skip':label['reason']}
                else:
                    raw=copy.deepcopy(label);raw.pop('photo_id');flags=raw['features']
                    if len(flags)!=len(set(flags)):raise ValueError('Duplicate feature flag')
                    raw['features']={flag:flag in flags for flag in allowed}
                    raw['signs_or_writing']={'present':raw.pop('signs_present'),'description':raw.pop('signs_description')}
                    for prefix,key in DISTANCES.items():
                        raw[key]={'description':raw.pop(prefix+'_description'),'distance_meters':raw.pop(prefix+'_m')}
                entries.append({'photo_id':pid,'analysis':raw})
            except ValueError as error:
                entries.append({'photo_id':pid,'adapter_error':str(error)})
    return entries
