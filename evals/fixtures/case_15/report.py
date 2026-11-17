from mathutils import mean


def summarize(values):
    return {'count': len(values), 'mean': mean(values)}
