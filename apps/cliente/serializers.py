from apps.citas.serializers import CitaSerializer


class ClienteCitaSerializer(CitaSerializer):
    # Serializer para reservar/reprogramar citas desde la vista cliente.
    # Inyecta codigo_cliente desde el token, no desde el frontend.
    def to_internal_value(self, data):
        data = data.copy()
        cliente = self.context.get('cliente')
        if cliente:
            data['codigo_cliente'] = cliente.codigo
        return super().to_internal_value(data)
