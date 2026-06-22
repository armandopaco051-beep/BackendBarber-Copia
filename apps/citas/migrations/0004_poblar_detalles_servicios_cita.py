from django.db import migrations


def poblar_detalles_servicios_cita(apps, schema_editor):
    Cita = apps.get_model('citas', 'Cita')
    DetalleServicioCita = apps.get_model('citas', 'DetalleServicioCita')

    for cita in Cita.objects.select_related('id_servicio').all():
        if not cita.id_servicio_id:
            continue

        DetalleServicioCita.objects.get_or_create(
            id_cita=cita,
            id_servicio=cita.id_servicio,
            defaults={
                'precio_unitario': cita.id_servicio.precio,
                'duracion_minutos': cita.id_servicio.duracion_minutos,
                'subtotal': cita.id_servicio.precio,
            },
        )
        total = sum(
            detalle.subtotal
            for detalle in DetalleServicioCita.objects.filter(id_cita=cita)
        )
        cita.subtotal_servicios = total
        cita.total_estimado = total
        cita.save(update_fields=['subtotal_servicios', 'total_estimado'])


class Migration(migrations.Migration):

    dependencies = [
        ('citas', '0003_cita_subtotal_servicios_cita_total_estimado_and_more'),
    ]

    operations = [
        migrations.RunPython(poblar_detalles_servicios_cita, migrations.RunPython.noop),
    ]
