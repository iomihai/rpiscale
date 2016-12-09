CREATE SEQUENCE weight_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE weight_id_seq OWNER TO rpiscale;

CREATE TABLE weight (
    id integer DEFAULT nextval('weight_id_seq'::regclass) NOT NULL,
    date_taken timestamp with time zone DEFAULT now() NOT NULL,
    weight double precision,
    name character varying(100),
    stdev double precision
);

ALTER TABLE weight OWNER TO rpiscale;

ALTER TABLE ONLY weight
    ADD CONSTRAINT weight_pkey PRIMARY KEY (id);
   
CREATE INDEX weight_date_taken ON weight USING btree (date_taken);

CREATE INDEX weight_name ON weight USING btree (name);
