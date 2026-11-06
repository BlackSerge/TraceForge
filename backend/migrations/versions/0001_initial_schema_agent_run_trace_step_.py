"""initial schema: agent_run, trace_step, eval tables

Revision ID: 0001
Revises: 
Create Date: 2026-11-05 15:48:52.219692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('eval_case',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.Text(), nullable=False),
    sa.Column('repo_url', sa.Text(), nullable=False),
    sa.Column('issue_url', sa.Text(), nullable=True),
    sa.Column('issue_text', sa.Text(), nullable=True),
    sa.Column('expected', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('tool_tag', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_eval_case')),
    sa.UniqueConstraint('slug', name=op.f('uq_eval_case_slug'))
    )
    op.create_table('eval_run',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('git_sha', sa.Text(), nullable=True),
    sa.Column('model', sa.Text(), nullable=True),
    sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_eval_run'))
    )
    op.create_table('agent_run',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('issue_url', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'running', 'awaiting_approval', 'approved', 'rejected', 'failed', name='run_status'), server_default='pending', nullable=False),
    sa.Column('eval_run_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('total_cost_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.ForeignKeyConstraint(['eval_run_id'], ['eval_run.id'], name=op.f('fk_agent_run_eval_run_id_eval_run'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_run'))
    )
    op.create_index(op.f('ix_agent_run_eval_run_id'), 'agent_run', ['eval_run_id'], unique=False)
    op.create_table('eval_result',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('eval_run_id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('agent_run_id', sa.UUID(), nullable=False),
    sa.Column('passed', sa.Boolean(), nullable=False),
    sa.Column('steps', sa.Integer(), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Numeric(precision=12, scale=6), nullable=False),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['agent_run_id'], ['agent_run.id'], name=op.f('fk_eval_result_agent_run_id_agent_run'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['case_id'], ['eval_case.id'], name=op.f('fk_eval_result_case_id_eval_case'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['eval_run_id'], ['eval_run.id'], name=op.f('fk_eval_result_eval_run_id_eval_run'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_eval_result')),
    sa.UniqueConstraint('agent_run_id', name=op.f('uq_eval_result_agent_run_id')),
    sa.UniqueConstraint('eval_run_id', 'case_id', name='uq_eval_result_eval_run_id_case_id')
    )
    op.create_index(op.f('ix_eval_result_case_id'), 'eval_result', ['case_id'], unique=False)
    op.create_table('trace_step',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('step_id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('agent_role', sa.Text(), server_default='coder', nullable=False),
    sa.Column('input_context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('tool_calls', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('reasoning_summary', sa.Text(), server_default='', nullable=False),
    sa.Column('outcome', sa.Enum('success', 'error', 'retry', 'stopped', name='step_outcome'), nullable=False),
    sa.Column('attempt', sa.SmallInteger(), server_default='1', nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('tokens_in', sa.Integer(), nullable=True),
    sa.Column('tokens_out', sa.Integer(), nullable=True),
    sa.Column('cost_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('model', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['agent_run.id'], name=op.f('fk_trace_step_run_id_agent_run'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_trace_step')),
    sa.UniqueConstraint('run_id', 'step_id', name='uq_trace_step_run_id_step_id')
    )
    op.create_index(op.f('ix_trace_step_timestamp'), 'trace_step', ['timestamp'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_trace_step_timestamp'), table_name='trace_step')
    op.drop_table('trace_step')
    op.drop_index(op.f('ix_eval_result_case_id'), table_name='eval_result')
    op.drop_table('eval_result')
    op.drop_index(op.f('ix_agent_run_eval_run_id'), table_name='agent_run')
    op.drop_table('agent_run')
    op.drop_table('eval_run')
    op.drop_table('eval_case')
    postgresql.ENUM(name='step_outcome').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='run_status').drop(op.get_bind(), checkfirst=True)
