import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerorder',
            name='customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='store_orders', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='customerorder',
            name='order_reference',
            field=models.CharField(blank=True, max_length=36, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='customerorder',
            name='order_reference',
            field=models.CharField(blank=True, default=uuid.uuid4, max_length=36, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='customerorder',
            name='payment_status',
            field=models.CharField(blank=True, choices=[('Pending', 'Pending')], max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='customerorder',
            name='payment_status',
            field=models.CharField(blank=True, choices=[('Pending', 'Pending')], default='Pending', max_length=20, null=True),
        ),
        migrations.CreateModel(
            name='CustomerOrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_name', models.CharField(max_length=160)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('quantity', models.PositiveIntegerField()),
                ('line_subtotal', models.DecimalField(decimal_places=2, max_digits=12)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='store.customerorder')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='order_items', to='store.product')),
            ],
        ),
    ]
