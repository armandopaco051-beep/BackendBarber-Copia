# Generated manually for CU12 promotions support.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('citas', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Promocion',
            fields=[
                ('id_promocion', models.AutoField(primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=150)),
                ('descripcion', models.TextField(blank=True)),
                ('tipo_descuento', models.CharField(choices=[('PORCENTAJE', 'Porcentaje'), ('MONTO', 'Monto')], max_length=20)),
                ('valor_descuento', models.DecimalField(decimal_places=2, max_digits=10)),
                ('fecha_inicio', models.DateField()),
                ('fecha_fin', models.DateField()),
                ('estado', models.CharField(choices=[('ACTIVO', 'Activo'), ('PROGRAMADA', 'Programada'), ('INACTIVO', 'Inactivo')], default='PROGRAMADA', max_length=20)),
                ('fecha_registro', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Promocion',
                'verbose_name_plural': 'Promociones',
                'db_table': '"agenda"."promocion"',
                'ordering': ['-fecha_inicio', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='DetallePromocion',
            fields=[
                ('id_detalle', models.AutoField(primary_key=True, serialize=False)),
                ('id_promocion', models.ForeignKey(db_column='id_promocion', on_delete=django.db.models.deletion.CASCADE, related_name='detalles_servicios', to='citas.promocion')),
                ('id_servicio', models.ForeignKey(db_column='id_servicio', on_delete=django.db.models.deletion.CASCADE, related_name='detalles_promociones', to='servicios.servicio')),
            ],
            options={
                'verbose_name': 'Detalle de promocion',
                'verbose_name_plural': 'Detalles de promociones',
                'db_table': '"agenda"."detalle_promocion"',
                'ordering': ['id_promocion', 'id_servicio'],
                'unique_together': {('id_promocion', 'id_servicio')},
            },
        ),
        migrations.AddField(
            model_name='promocion',
            name='servicios',
            field=models.ManyToManyField(blank=True, related_name='promociones', through='citas.DetallePromocion', to='servicios.servicio'),
        ),
    ]
